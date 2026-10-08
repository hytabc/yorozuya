"""Voxel houses: immutable furniture versions, account-owned saves and read-only visits."""
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import secrets
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from pydantic import Field, StrictInt, model_validator
from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_content_moderator, get_current_user, get_optional_user
from .images import normalize_image, AVATAR_SIGNATURES
from .media import commit_moderation, delete_media, media_url, write_media
from .models import User
from .ratelimit import enforce
from .schemas import RequestModel


def now():
    return datetime.now(timezone.utc).isoformat()


class HouseRoom(Base):
    __tablename__ = 'house_rooms'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    state_json: Mapped[str] = mapped_column(Text)
    share_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class HouseFurniture(Base):
    __tablename__ = 'house_furniture'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    style: Mapped[str] = mapped_column(String(32))
    thumbnail: Mapped[str | None] = mapped_column(String(160), nullable=True)
    version_id: Mapped[str] = mapped_column(String(64))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class HouseVersion(Base):
    __tablename__ = 'house_furniture_versions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    furniture_id: Mapped[str] = mapped_column(String(64), index=True)
    data_json: Mapped[str] = mapped_column(Text)


class HouseTexture(Base):
    __tablename__ = 'house_textures'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(64))
    file_path: Mapped[str] = mapped_column(String(160), unique=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    moderated: Mapped[bool] = mapped_column(Boolean, default=False)


class HouseLike(Base):
    __tablename__ = 'house_likes'
    __table_args__ = (UniqueConstraint('room_id', 'user_id', name='uq_house_like'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int] = mapped_column(Integer)


class HouseComment(Base):
    __tablename__ = 'house_comments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


@lru_cache(maxsize=1)
def catalog():
    return json.loads(Path(__file__).with_name('house_catalog.json').read_text())


def seed_house_catalog(db: Session):
    existing = set(db.scalars(select(HouseFurniture.id)).all())
    for model in catalog()['models']:
        if model['id'] in existing:
            continue
        version_id = model['id'] + '-v1'
        data = {k: model[k] for k in ('gridSize', 'mount', 'palette', 'voxels')}
        db.add(HouseVersion(id=version_id, furniture_id=model['id'], data_json=json.dumps(data, separators=(',', ':'))))
        db.add(HouseFurniture(id=model['id'], user_id=None, name=model['name'], category=model['category'],
                              style=model['style'], thumbnail=model['thumbnail'], version_id=version_id, is_public=True))
    db.commit()


class Slot(RequestModel):
    key: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,31}$')
    label: str = Field(min_length=1, max_length=32)
    color: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    editable: bool = True


class VoxelData(RequestModel):
    gridSize: Literal[16, 32, 64]
    mount: Literal['floor', 'surface', 'wall', 'ceiling'] = 'floor'
    palette: list[Slot] = Field(min_length=1, max_length=256)
    voxels: list[tuple[StrictInt, StrictInt, StrictInt, StrictInt]] = Field(min_length=1, max_length=262144)

    @model_validator(mode='after')
    def validate_voxels(self):
        if len({s.key for s in self.palette}) != len(self.palette):
            raise ValueError('改色部位重复')
        occupied = set()
        for x, y, z, color in self.voxels:
            if not all(0 <= a < self.gridSize for a in (x, y, z)) or not 0 <= color < len(self.palette):
                raise ValueError('体素坐标或色板索引无效')
            if (x, y, z) in occupied:
                raise ValueError('体素坐标重复')
            occupied.add((x, y, z))
        return self


class FurnitureSave(RequestModel):
    revision: int = Field(default=0, ge=0)
    name: str = Field(min_length=1, max_length=64)
    category: str = Field(max_length=32)
    style: str = Field(default='自制', max_length=32)
    data: VoxelData


class Position(RequestModel):
    x: StrictInt = Field(ge=0, lt=256)
    y: StrictInt = Field(ge=0, lt=256)
    z: StrictInt = Field(ge=0, lt=128)


class Placement(RequestModel):
    id: str = Field(min_length=1, max_length=64)
    versionId: str = Field(min_length=1, max_length=64)
    position: Position
    rotation: Literal[0, 90, 180, 270] = 0
    paletteOverrides: dict[str, str] = Field(default_factory=dict, max_length=256)


class Material(RequestModel):
    color: str = Field(default='#eee5d5', pattern=r'^#[0-9a-fA-F]{6}$')
    textureId: str | None = Field(default=None, max_length=64)
    mode: Literal['repeat', 'stretch'] = 'repeat'


class RoomState(RequestModel):
    schemaVersion: Literal[1] = 1
    name: str = Field(default='我的小屋', min_length=1, max_length=64)
    placements: list[Placement] = Field(default_factory=list, max_length=128)
    floor: Material = Field(default_factory=Material)
    wall: Material = Field(default_factory=lambda: Material(color='#f2eee5'))


class RoomSave(RequestModel):
    revision: int = Field(ge=0)
    state: RoomState


class Visibility(RequestModel):
    is_visible: bool


class PublicFlag(RequestModel):
    enabled: bool


class CommentCreate(RequestModel):
    content: str = Field(min_length=1, max_length=1000)


def user_public(db, user_id, viewer=None):
    # Import at call time, avoiding a circular dependency while retaining media-aware presentation.
    from .main import present_user_public
    user = db.get(User, user_id)
    return present_user_public(user, viewer).model_dump(mode='json') if user else None


def furniture_card(f):
    return {'id': f.id, 'name': f.name, 'category': f.category, 'style': f.style, 'thumbnail': f.thumbnail,
            'versionId': f.version_id, 'revision': f.revision, 'creatorId': f.user_id,
            'isPublic': f.is_public, 'isVisible': f.is_visible, 'deleted': f.deleted}


def texture_card(t, viewer=None):
    allowed = t.is_visible or viewer and (viewer.id == t.user_id or is_moderator(viewer))
    return {'id': f'upload-{t.id}', 'recordId': t.id, 'name': t.name, 'creatorId': t.user_id,
            'isVisible': t.is_visible, 'moderated': t.moderated,
            'url': media_url(t.file_path, public=t.is_visible) if allowed else None}


def is_moderator(user):
    from .models import UserRole
    return bool(user and (user.is_admin or user.role in (UserRole.STAFF, UserRole.DISCIPLINARIAN)))


def transformed(voxels, rotation):
    coords = [(x,y,z) if rotation==0 else (-y,x,z) if rotation==90 else (-x,-y,z) if rotation==180 else (y,-x,z) for x,y,z,c in voxels]
    lo = [min(p[a] for p in coords) for a in range(3)]
    return [(x-lo[0],y-lo[1],z-lo[2]) for x,y,z in coords]


def versions_for(db, ids):
    if not ids: return {}
    return {v.id: (v, f) for v, f in db.execute(select(HouseVersion, HouseFurniture).join(
        HouseFurniture, HouseFurniture.id == HouseVersion.furniture_id).where(HouseVersion.id.in_(ids)))}


def validate_room(db, state, user, old_state):
    ids = [p.id for p in state.placements]
    if len(set(ids)) != len(ids): raise HTTPException(422, '家具放置项编号重复')
    old_ids = {p['versionId'] for p in old_state.get('placements', [])}
    rows = versions_for(db, {p.versionId for p in state.placements})
    occupied = set()
    for p in state.placements:
        pair = rows.get(p.versionId)
        if not pair: raise HTTPException(422, '引用的家具版本不存在')
        version, furniture = pair
        if p.versionId not in old_ids and (furniture.deleted or not furniture.is_visible or
                not (furniture.is_public or furniture.user_id == user.id)):
            raise HTTPException(403, '无法放置此家具')
        data = json.loads(version.data_json)
        editable = {s['key'] for s in data['palette'] if s['editable']}
        import re
        if any(k not in editable or not re.fullmatch(r'#[0-9a-fA-F]{6}', c) for k,c in p.paletteOverrides.items()):
            raise HTTPException(422, '改色部位或颜色无效')
        points=transformed(data['voxels'], p.rotation)
        if len(occupied)+len(points)>1_000_000: raise HTTPException(422, '房间累计体素超过100万')
        for x,y,z in points:
            q=(x+p.position.x,y+p.position.y,z+p.position.z)
            if q[0]>=256 or q[1]>=256 or q[2]>=128: raise HTTPException(422, '家具超出房间边界')
            if q in occupied: raise HTTPException(422, '家具之间不能重叠')
            occupied.add(q)
    builtin = {t['id'] for t in catalog()['textures']}
    for material in (state.floor, state.wall):
        if not material.textureId or material.textureId in builtin: continue
        t = texture_by_id(db, material.textureId)
        if not t or not (t.user_id == user.id or t.is_visible): raise HTTPException(422, '纹理不存在或不可使用')


def texture_by_id(db, ident):
    if not ident or not ident.startswith('upload-') or not ident[7:].isdigit(): return None
    return db.get(HouseTexture, int(ident[7:]))


def room_out(db, room, viewer, private=False):
    state=json.loads(room.state_json) if room else RoomState().model_dump()
    rows=versions_for(db,{p['versionId'] for p in state['placements']})
    assets={}; hidden=[]
    for ident,(version,furniture) in rows.items():
        if not furniture.is_visible and not private:
            hidden.append(ident); continue
        assets[ident]={'data':json.loads(version.data_json),'furniture':furniture_card(furniture)}
    if not private: state['placements']=[p for p in state['placements'] if p['versionId'] in assets]
    texture_urls={}
    for key in ('floor','wall'):
        material=state[key]; ident=material.get('textureId')
        builtin=next((t for t in catalog()['textures'] if t['id']==ident),None)
        texture=texture_by_id(db,ident)
        if builtin: texture_urls[ident]=builtin['url']
        elif texture and (texture.is_visible or private): texture_urls[ident]=texture_card(texture,viewer)['url']
        else: material['textureId']=None
    likes = db.scalar(select(func.count()).select_from(HouseLike).where(HouseLike.room_id==room.id)) if room else 0
    liked=bool(room and viewer and db.scalar(select(HouseLike.id).where(HouseLike.room_id==room.id,HouseLike.user_id==viewer.id)))
    result={'revision':room.revision if room else 0,'state':state,'assets':assets,'textureUrls':texture_urls,
            'updatedAt':room.updated_at if room else None,'likeCount':likes,'liked':liked}
    if room:
        result.update(owner=user_public(db,room.user_id,viewer),shareId=room.share_id,isVisible=room.is_visible)
    return result


def shared_room(db, share_id):
    room=db.scalar(select(HouseRoom).where(HouseRoom.share_id==share_id,HouseRoom.is_visible.is_(True)))
    if not room: raise HTTPException(404, '房屋不存在或已关闭分享')
    return room


def paginated(db, query, page, page_size, present):
    total=db.scalar(select(func.count()).select_from(query.subquery())) or 0
    return {'total':total,'page':page,'page_size':page_size,'items':[present(x) for x in db.scalars(query.offset((page-1)*page_size).limit(page_size))]}


router=APIRouter(prefix='/api/house',tags=['house'])


@router.get('/catalog')
def read_catalog():
    return {k: v for k,v in catalog().items() if k!='models'}


@router.get('/furniture')
def furniture_list(page: int=Query(1,ge=1),page_size: int=Query(20,ge=1,le=50),category: str='',style: str='',search: str='',
                   mine: bool=False,user: User|None=Depends(get_optional_user),db:Session=Depends(get_db)):
    query=select(HouseFurniture).where(HouseFurniture.deleted.is_(False))
    if mine:
        if not user: raise HTTPException(401,'请先登录')
        query=query.where(HouseFurniture.user_id==user.id)
    else: query=query.where(HouseFurniture.is_public.is_(True),HouseFurniture.is_visible.is_(True))
    if category: query=query.where(HouseFurniture.category==category)
    if style: query=query.where(HouseFurniture.style==style)
    if search: query=query.where(HouseFurniture.name.contains(search[:64],autoescape=True))
    return paginated(db,query.order_by(HouseFurniture.id),page,page_size,furniture_card)


@router.get('/versions/{version_id}')
def read_version(version_id:str,user:User|None=Depends(get_optional_user),db:Session=Depends(get_db)):
    pair=versions_for(db,[version_id]).get(version_id)
    if not pair: raise HTTPException(404,'家具不存在')
    version,f=pair
    owner=user and f.user_id==user.id
    if not owner and not is_moderator(user) and (not f.is_public or not f.is_visible or f.deleted):
        raise HTTPException(404,'家具不可用')
    return {'data':json.loads(version.data_json),'furniture':furniture_card(f)}


@router.put('/furniture/{furniture_id}')
def save_furniture(furniture_id:str,payload:FurnitureSave,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    enforce('house-furniture',str(user.id),60,600)
    if payload.category not in {c['id'] for c in catalog()['categories']}: raise HTTPException(422,'家具类别无效')
    if len(furniture_id)>64 or not furniture_id or furniture_id.startswith('official-'): raise HTTPException(422,'家具编号无效')
    encoded=json.dumps(payload.data.model_dump(),separators=(',',':'))
    if len(encoded.encode())>8*1024*1024: raise HTTPException(413,'家具数据超过8 MiB')
    f=db.get(HouseFurniture,furniture_id); version_id=uuid4().hex
    if f:
        if f.user_id!=user.id or f.deleted: raise HTTPException(403,'只能修改自己的家具')
        result=db.execute(update(HouseFurniture).where(HouseFurniture.id==furniture_id,HouseFurniture.revision==payload.revision).values(
            revision=payload.revision+1,version_id=version_id,name=payload.name,category=payload.category,style=payload.style,updated_at=now()))
        if result.rowcount!=1: db.rollback(); raise HTTPException(409,'家具已被其他页面更新，请重新载入')
    else:
        if payload.revision!=0: raise HTTPException(409,'家具版本不一致')
        db.add(HouseFurniture(id=furniture_id,user_id=user.id,name=payload.name,category=payload.category,style=payload.style,version_id=version_id))
    db.add(HouseVersion(id=version_id,furniture_id=furniture_id,data_json=encoded))
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409,'家具已被其他页面创建，请重新载入')
    return furniture_card(db.get(HouseFurniture,furniture_id))


@router.patch('/furniture/{furniture_id}/publish')
def publish_furniture(furniture_id:str,payload:PublicFlag,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    enforce('house-publish',str(user.id),20,600)
    f=db.get(HouseFurniture,furniture_id)
    if not f or f.user_id!=user.id or f.deleted: raise HTTPException(403,'只能发布自己的家具')
    f.is_public=payload.enabled; db.commit(); return furniture_card(f)


@router.delete('/furniture/{furniture_id}')
def remove_furniture(furniture_id:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    f=db.get(HouseFurniture,furniture_id)
    if not f or f.user_id!=user.id: raise HTTPException(403,'只能删除自己的家具')
    f.deleted=True; f.is_public=False; db.commit(); return Response(status_code=204)


@router.get('/room')
def read_room(user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return room_out(db,db.scalar(select(HouseRoom).where(HouseRoom.user_id==user.id)),user,True)


@router.put('/room')
def save_room(payload:RoomSave,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    enforce('house-save',str(user.id),120,600)
    room=db.scalar(select(HouseRoom).where(HouseRoom.user_id==user.id))
    if payload.revision!=(room.revision if room else 0): raise HTTPException(409,'房屋已被其他页面更新，请保留草稿并重新载入')
    validate_room(db,payload.state,user,json.loads(room.state_json) if room else {})
    values={'state_json':json.dumps(payload.state.model_dump(),separators=(',',':')),'revision':payload.revision+1,'updated_at':now()}
    if room:
        result=db.execute(update(HouseRoom).where(HouseRoom.id==room.id,HouseRoom.revision==payload.revision).values(**values))
        if result.rowcount!=1: db.rollback(); raise HTTPException(409,'房屋已被其他页面更新')
    else: db.add(HouseRoom(user_id=user.id,**values))
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409,'房屋已被其他页面创建')
    return {'revision':values['revision'],'updatedAt':values['updated_at']}


@router.patch('/room/share')
def share_room(payload:PublicFlag,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    enforce('house-share',str(user.id),20,600)
    room=db.scalar(select(HouseRoom).where(HouseRoom.user_id==user.id))
    if not room: raise HTTPException(409,'请先保存房屋')
    if payload.enabled and not room.is_visible: raise HTTPException(403,'房屋已被屏蔽，恢复后才能开启分享')
    if payload.enabled and not room.share_id: room.share_id=secrets.token_urlsafe(24)
    elif not payload.enabled: room.share_id=None
    db.commit(); return {'shareId':room.share_id}


@router.get('/visit/{share_id}')
def visit(share_id:str,user:User|None=Depends(get_optional_user),db:Session=Depends(get_db)):
    return room_out(db,shared_room(db,share_id),user)


@router.get('/users/{user_id}')
def creator(user_id:int,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=50),viewer:User|None=Depends(get_optional_user),db:Session=Depends(get_db)):
    if not db.get(User,user_id): raise HTTPException(404,'用户不存在')
    room=db.scalar(select(HouseRoom).where(HouseRoom.user_id==user_id,HouseRoom.is_visible.is_(True),HouseRoom.share_id.is_not(None)))
    items=paginated(db,select(HouseFurniture).where(HouseFurniture.user_id==user_id,HouseFurniture.is_public.is_(True),HouseFurniture.is_visible.is_(True),HouseFurniture.deleted.is_(False)).order_by(HouseFurniture.updated_at.desc()),page,page_size,furniture_card)
    return {'user':user_public(db,user_id,viewer),'shareId':room.share_id if room else None,'furniture':items}


@router.put('/visit/{share_id}/like')
def like(share_id:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    enforce('house-like',str(user.id),60,600); room=shared_room(db,share_id)
    db.add(HouseLike(room_id=room.id,user_id=user.id))
    try: db.commit()
    except IntegrityError: db.rollback()
    return {'liked':True,'likeCount':db.scalar(select(func.count()).select_from(HouseLike).where(HouseLike.room_id==room.id))}


@router.delete('/visit/{share_id}/like')
def unlike(share_id:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    enforce('house-like',str(user.id),60,600); room=shared_room(db,share_id)
    item=db.scalar(select(HouseLike).where(HouseLike.room_id==room.id,HouseLike.user_id==user.id))
    if item: db.delete(item)
    db.commit(); return {'liked':False,'likeCount':db.scalar(select(func.count()).select_from(HouseLike).where(HouseLike.room_id==room.id))}


def comment_out(db,c,user,room):
    return {'id':c.id,'content':c.content,'createdAt':c.created_at,'user':user_public(db,c.user_id,user),
            'canDelete':bool(user and (user.id in (c.user_id,room.user_id) or is_moderator(user)))}


@router.get('/visit/{share_id}/comments')
def comments(share_id:str,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=50),user:User|None=Depends(get_optional_user),db:Session=Depends(get_db)):
    room=shared_room(db,share_id)
    return paginated(db,select(HouseComment).where(HouseComment.room_id==room.id).order_by(HouseComment.id.desc()),page,page_size,lambda c:comment_out(db,c,user,room))


@router.post('/visit/{share_id}/comments',status_code=201)
def post_comment(share_id:str,payload:CommentCreate,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    enforce('house-comment',str(user.id),20,600); room=shared_room(db,share_id)
    if not payload.content.strip(): raise HTTPException(422,'留言不能为空')
    c=HouseComment(room_id=room.id,user_id=user.id,content=payload.content.strip()); db.add(c); db.commit()
    return comment_out(db,c,user,room)


@router.delete('/comments/{comment_id}')
def delete_comment(comment_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    c=db.get(HouseComment,comment_id)
    if not c: raise HTTPException(404,'留言不存在')
    room=db.get(HouseRoom,c.room_id)
    if user.id not in (c.user_id,room.user_id) and not is_moderator(user): raise HTTPException(403,'没有删除权限')
    db.delete(c); db.commit(); return Response(status_code=204)


@router.get('/textures')
def textures_list(user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return [texture_card(t,user) for t in db.scalars(select(HouseTexture).where(HouseTexture.user_id==user.id))]


@router.post('/textures',status_code=201)
async def upload_texture(file:UploadFile=File(...),user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    enforce('upload',str(user.id),30,3600)
    content=await file.read(10*1024*1024+1)
    if len(content)>10*1024*1024: raise HTTPException(413,'纹理图片不能超过10 MB')
    ext,clean=normalize_image(content,allowed=AVATAR_SIGNATURES,format_hint='仅支持 PNG 或 JPEG 纹理')
    key=f'house/{uuid4().hex}{ext}'
    t=HouseTexture(user_id=user.id,name=(file.filename or '自定义纹理')[:64],file_path=key)
    try:
        write_media(key,clean,public=False); db.add(t); db.commit()
    except Exception:
        db.rollback(); delete_media(key); raise HTTPException(503,'纹理保存失败，请稍后重试')
    return texture_card(t,user)


@router.delete('/textures/{texture_id}')
def delete_texture(texture_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    t=db.get(HouseTexture,texture_id)
    if not t or t.user_id!=user.id: raise HTTPException(403,'只能删除自己的纹理')
    delete_media(t.file_path); db.delete(t); db.commit(); return Response(status_code=204)


admin_router=APIRouter(prefix='/api/admin/house',tags=['house moderation'],dependencies=[Depends(get_content_moderator)])


@admin_router.get('/{kind}')
def moderation_list(kind:Literal['rooms','furniture','textures'],page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=50),user:User=Depends(get_content_moderator),db:Session=Depends(get_db)):
    if kind=='textures': return paginated(db,select(HouseTexture).order_by(HouseTexture.id.desc()),page,page_size,lambda t:texture_card(t,user))
    if kind=='furniture': return paginated(db,select(HouseFurniture).where(HouseFurniture.user_id.is_not(None),HouseFurniture.deleted.is_(False)).order_by(HouseFurniture.updated_at.desc()),page,page_size,furniture_card)
    return paginated(db,select(HouseRoom).order_by(HouseRoom.updated_at.desc()),page,page_size,lambda r:{'id':r.id,'name':json.loads(r.state_json)['name'],'creatorId':r.user_id,'isVisible':r.is_visible,'shareId':r.share_id})


@admin_router.get('/rooms/{room_id}/preview')
def room_preview(room_id:str,user:User=Depends(get_content_moderator),db:Session=Depends(get_db)):
    room=db.get(HouseRoom,room_id)
    if not room: raise HTTPException(404,'房屋不存在')
    return room_out(db,room,user,True)


@admin_router.patch('/{kind}/{ident}')
def moderate(kind:Literal['rooms','furniture','textures'],ident:str,payload:Visibility,user:User=Depends(get_content_moderator),db:Session=Depends(get_db)):
    model={'rooms':HouseRoom,'furniture':HouseFurniture,'textures':HouseTexture}[kind]
    if kind=='textures' and not ident.isdigit(): raise HTTPException(404,'纹理不存在')
    item=db.get(model,int(ident) if kind=='textures' else ident)
    if not item: raise HTTPException(404,'内容不存在')
    item.is_visible=payload.is_visible
    if kind=='textures': item.moderated=True; commit_moderation(db,item.file_path,public=payload.is_visible)
    else: db.commit()
    return {'isVisible':item.is_visible}
