"""Virtual-life content packs: database storage, validation and admin API.

A pack holds the FULL site content (NPCs, portraits, worlds, rooms, presence,
actions, node-graph dialogue, initial state) as JSON. Exactly one pack is
active; save validation (virtual_life.py) and the game client both consume
the active pack. The JSON file under app/life_packs/ is only a startup seed.
"""
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .config import settings
from .database import Base, get_db
from .dependencies import get_role_manager
from .models import User

SEED_DIR = Path(__file__).resolve().parent / 'life_packs'
DEFAULT_PACK_ID = 'wsw-default-life'
STAT_KEYS = {'mood', 'energy', 'social', 'explore'}
PRESENCE_STATUSES = {'green', 'orange', 'red', 'offline'}
PACK_ID_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{0,99}$')


class VirtualLifePack(Base):
    __tablename__ = "virtual_life_packs"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class PackContentError(ValueError):
    pass


def _fail(message: str):
    raise PackContentError(message)


def validate_pack_content(content) -> dict:
    """Structural and reference-consistency checks; returns the content unchanged."""
    if not isinstance(content, dict):
        _fail('内容必须是对象')
    npc_ids = content.get('npcIds')
    if not isinstance(npc_ids, list) or not npc_ids or len(set(npc_ids)) != len(npc_ids):
        _fail('npcIds 必须是非空且不重复的数组')
    ids = set(npc_ids)

    npcs = content.get('npcs')
    if not isinstance(npcs, list) or {n.get('id') for n in npcs if isinstance(n, dict)} != ids:
        _fail('npcs 必须与 npcIds 一一对应')
    for npc in npcs:
        if not isinstance(npc.get('name'), str) or not npc['name']:
            _fail(f"NPC {npc.get('id')} 缺少名字")
        if not isinstance(npc.get('bond'), int) or not 0 <= npc['bond'] <= 100:
            _fail(f"NPC {npc.get('id')} 初始好感必须在 0-100")

    portraits = content.get('portraits')
    if not isinstance(portraits, dict) or set(portraits) != ids:
        _fail('portraits 必须覆盖全部 NPC')
    if any(not isinstance(path, str) or not path for path in portraits.values()):
        _fail('portraits 存在空路径')

    worlds = content.get('worlds')
    if not isinstance(worlds, list) or not worlds:
        _fail('worlds 不能为空')
    world_ids = set()
    for world in worlds:
        if not isinstance(world.get('id'), str) or not world['id'] or world['id'] in world_ids:
            _fail('world id 缺失或重复')
        world_ids.add(world['id'])
        if not isinstance(world.get('name'), str) or not world['name']:
            _fail(f"世界 {world['id']} 缺少名称")

    rooms = content.get('rooms')
    if not isinstance(rooms, list) or not rooms:
        _fail('rooms 不能为空')
    room_ids = set()
    for room in rooms:
        if not isinstance(room.get('id'), str) or not room['id'] or room['id'] in room_ids:
            _fail('room id 缺失或重复')
        room_ids.add(room['id'])
        if room.get('worldId') not in world_ids:
            _fail(f"房间 {room['id']} 指向未知世界 {room.get('worldId')}")
        if not isinstance(room.get('capacity'), int) or room['capacity'] < 1:
            _fail(f"房间 {room['id']} 容量无效")
        if not isinstance(room.get('occupants'), int) or room['occupants'] < 0:
            _fail(f"房间 {room['id']} 人数无效")

    presence = content.get('presence')
    if not isinstance(presence, dict) or set(presence) != ids:
        _fail('presence 必须覆盖全部 NPC')
    for npc_id, p in presence.items():
        if p.get('status') not in PRESENCE_STATUSES:
            _fail(f"{npc_id} 的在线状态无效")
        if p.get('roomId') is not None and p.get('roomId') not in room_ids:
            _fail(f"{npc_id} 指向未知房间 {p.get('roomId')}")

    actions = content.get('actions')
    if not isinstance(actions, list) or not actions:
        _fail('actions 不能为空')
    action_ids = set()
    for action in actions:
        if not isinstance(action.get('id'), str) or not action['id'] or action['id'] in action_ids:
            _fail('action id 缺失或重复')
        action_ids.add(action['id'])
        if not isinstance(action.get('label'), str) or not action['label']:
            _fail(f"动作 {action['id']} 缺少名称")
        if not isinstance(action.get('reward'), int) or not 0 <= action['reward'] <= 100:
            _fail(f"动作 {action['id']} 奖励数值无效")
        if not isinstance(action.get('threshold'), int) or not 0 <= action['threshold'] <= 100:
            _fail(f"动作 {action['id']} 好感门槛无效")
        if not isinstance(action.get('reply'), str) or not action['reply']:
            _fail(f"动作 {action['id']} 缺少反馈文案")

    dialogue = content.get('dialogue')
    if not isinstance(dialogue, dict) or set(dialogue) != ids:
        _fail('dialogue 必须覆盖全部 NPC')
    for npc_id, script in dialogue.items():
        nodes = script.get('nodes')
        if not isinstance(nodes, dict) or not nodes:
            _fail(f"{npc_id} 的剧本没有节点")
        if script.get('start') not in nodes:
            _fail(f"{npc_id} 的剧本起点无效")
        for node_id, node in nodes.items():
            if not isinstance(node.get('line'), str) or not node['line']:
                _fail(f"{npc_id}/{node_id} 缺少台词")
            choices = node.get('choices')
            if not isinstance(choices, list) or not choices:
                _fail(f"{npc_id}/{node_id} 缺少选项")
            for choice in choices:
                if not isinstance(choice.get('label'), str) or not choice['label']:
                    _fail(f"{npc_id}/{node_id} 存在无文案选项")
                if not isinstance(choice.get('reply'), str) or not choice['reply']:
                    _fail(f"{npc_id}/{node_id} 存在无回复选项")
                if choice.get('next') is not None and choice.get('next') not in nodes:
                    _fail(f"{npc_id}/{node_id} 选项跳转到未知节点 {choice.get('next')}")
                effects = choice.get('effects') or {}
                if not isinstance(effects, dict):
                    _fail(f"{npc_id}/{node_id} 选项 effects 必须是对象")
                bond = effects.get('bond', 0)
                if not isinstance(bond, int) or not 0 <= bond <= 100:
                    _fail(f"{npc_id}/{node_id} 选项好感变化无效")
                stats = effects.get('stats', {})
                if not isinstance(stats, dict) or not set(stats).issubset(STAT_KEYS):
                    _fail(f"{npc_id}/{node_id} 选项包含未知属性")
                if any(not isinstance(v, int) or not -100 <= v <= 100 for v in stats.values()):
                    _fail(f"{npc_id}/{node_id} 选项属性变化无效")

    initial = content.get('initialState')
    if not isinstance(initial, dict):
        _fail('缺少 initialState')
    if not isinstance(initial.get('day'), int) or initial['day'] < 1:
        _fail('initialState.day 无效')
    stats = initial.get('stats')
    if not isinstance(stats, dict) or set(stats) != STAT_KEYS:
        _fail('initialState.stats 必须包含 mood/energy/social/explore')
    if any(not isinstance(v, int) or not 0 <= v <= 100 for v in stats.values()):
        _fail('initialState.stats 数值必须在 0-100')
    if not isinstance(initial.get('currentWorld'), str) or not initial['currentWorld']:
        _fail('initialState.currentWorld 缺失')
    conversations = initial.get('conversations')
    if not isinstance(conversations, dict) or set(conversations) != ids:
        _fail('initialState.conversations 必须覆盖全部 NPC')
    return content


def derive_save_rules(content: dict) -> dict:
    """Whitelists used by save validation, derived from pack content."""
    world_name = {w['id']: w['name'] for w in content['worlds']}
    enterable = [r for r in content['rooms']
                 if not r['private'] and 0 < r['occupants'] < r['capacity']]
    return {
        'npcIds': list(content['npcIds']),
        'actionIds': [a['id'] for a in content['actions']],
        'roomIds': [r['id'] for r in enterable],
        'roomWorlds': {r['id']: world_name[r['worldId']] for r in enterable},
        'dialogueNodes': {npc_id: set(script['nodes']) for npc_id, script in content['dialogue'].items()},
    }


def get_active_pack(db: Session) -> VirtualLifePack:
    pack = db.scalar(select(VirtualLifePack).where(VirtualLifePack.is_active.is_(True)))
    if pack is None:
        raise HTTPException(500, '站点尚未配置虚拟人生内容包')
    return pack


def get_save_rules(db: Session) -> dict:
    pack = get_active_pack(db)
    return derive_save_rules(json.loads(pack.content_json)) | {'packId': pack.id}


def seed_virtual_life_packs(db: Session) -> None:
    """First startup: load bundled JSON seeds; the default pack becomes active."""
    if db.scalar(select(VirtualLifePack.id).limit(1)) is not None:
        return
    now = datetime.now(timezone.utc).isoformat()
    for path in sorted(SEED_DIR.glob('*.json')):
        content = json.loads(path.read_text(encoding='utf-8'))
        validate_pack_content(content)
        db.add(VirtualLifePack(
            id=path.stem, name='默认内容包', version=1,
            content_json=json.dumps(content, ensure_ascii=False),
            is_active=path.stem == DEFAULT_PACK_ID, updated_at=now,
        ))
    db.commit()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PackCreate(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    content: dict


class PackUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    content: dict | None = None


class PackDuplicate(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)


router = APIRouter(prefix='/api/virtual-life', tags=['virtual-life-packs'])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summary(pack: VirtualLifePack) -> dict:
    return {'id': pack.id, 'name': pack.name, 'version': pack.version,
            'active': pack.is_active, 'updatedAt': pack.updated_at}


def _detail(pack: VirtualLifePack) -> dict:
    return _summary(pack) | {'content': json.loads(pack.content_json)}


def _get_pack_or_404(db: Session, pack_id: str) -> VirtualLifePack:
    pack = db.get(VirtualLifePack, pack_id)
    if pack is None:
        raise HTTPException(404, '内容包不存在')
    return pack


@router.get('/pack')
def read_active_pack(user: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    return _detail(get_active_pack(db))


@router.get('/packs')
def list_packs(user: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    packs = db.scalars(select(VirtualLifePack).order_by(VirtualLifePack.id)).all()
    return [_summary(pack) for pack in packs]


@router.post('/packs', status_code=201)
def create_pack(payload: PackCreate, user: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    if not PACK_ID_PATTERN.match(payload.id):
        raise HTTPException(422, '内容包 id 只能包含小写字母、数字和连字符')
    if db.get(VirtualLifePack, payload.id) is not None:
        raise HTTPException(409, '内容包 id 已存在')
    try:
        validate_pack_content(payload.content)
    except PackContentError as exc:
        raise HTTPException(422, f'内容包校验失败：{exc}')
    pack = VirtualLifePack(id=payload.id, name=payload.name, version=1,
                           content_json=json.dumps(payload.content, ensure_ascii=False),
                           is_active=False, updated_at=_utcnow())
    db.add(pack)
    db.commit()
    return _detail(pack)


@router.get('/packs/{pack_id}')
def read_pack(pack_id: str, user: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    return _detail(_get_pack_or_404(db, pack_id))


@router.put('/packs/{pack_id}')
def update_pack(pack_id: str, payload: PackUpdate, user: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    pack = _get_pack_or_404(db, pack_id)
    if payload.content is not None:
        try:
            validate_pack_content(payload.content)
        except PackContentError as exc:
            raise HTTPException(422, f'内容包校验失败：{exc}')
        pack.content_json = json.dumps(payload.content, ensure_ascii=False)
        pack.version += 1
    if payload.name is not None:
        pack.name = payload.name
    pack.updated_at = _utcnow()
    db.commit()
    return _detail(pack)


@router.post('/packs/{pack_id}/activate')
def activate_pack(pack_id: str, user: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    pack = _get_pack_or_404(db, pack_id)
    try:
        validate_pack_content(json.loads(pack.content_json))
    except PackContentError as exc:
        raise HTTPException(422, f'内容包校验失败，无法激活：{exc}')
    for other in db.scalars(select(VirtualLifePack).where(VirtualLifePack.is_active.is_(True))):
        other.is_active = False
    pack.is_active = True
    pack.updated_at = _utcnow()
    db.commit()
    return _detail(pack)


@router.post('/packs/{pack_id}/duplicate', status_code=201)
def duplicate_pack(pack_id: str, payload: PackDuplicate, user: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    source = _get_pack_or_404(db, pack_id)
    if not PACK_ID_PATTERN.match(payload.id):
        raise HTTPException(422, '内容包 id 只能包含小写字母、数字和连字符')
    if db.get(VirtualLifePack, payload.id) is not None:
        raise HTTPException(409, '内容包 id 已存在')
    pack = VirtualLifePack(id=payload.id, name=payload.name, version=1,
                           content_json=source.content_json, is_active=False, updated_at=_utcnow())
    db.add(pack)
    db.commit()
    return _detail(pack)


@router.delete('/packs/{pack_id}', status_code=204)
def delete_pack(pack_id: str, user: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    pack = _get_pack_or_404(db, pack_id)
    if pack.is_active:
        raise HTTPException(409, '活动中的内容包不能删除，请先激活其他内容包')
    db.delete(pack)
    db.commit()


# ==== 素材上传(世界背景图/NPC 立绘,阶段 4d) ====
# 与主站照片上传同一套约束:魔数嗅探、5 MiB 上限,落在 uploads 挂载目录的
# life/ 子目录,经 /uploads 静态挂载对外提供。
MAX_LIFE_IMAGE_BYTES = 5 * 1024 * 1024
LIFE_IMAGE_SIGNATURES = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def _life_image_extension(content: bytes):
    for signature, extension in LIFE_IMAGE_SIGNATURES:
        if content.startswith(signature):
            return extension
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp"
    return None


@router.post('/assets', status_code=201)
async def upload_life_asset(file: UploadFile = File(...), user: User = Depends(get_role_manager)):
    content = await file.read(MAX_LIFE_IMAGE_BYTES + 1)
    if not content:
        raise HTTPException(422, '上传的图片不能为空')
    if len(content) > MAX_LIFE_IMAGE_BYTES:
        raise HTTPException(422, '单张图片不能超过 5 MiB')
    extension = _life_image_extension(content)
    if extension is None:
        raise HTTPException(422, '仅支持 JPEG、PNG、GIF 或 WebP 图片')
    file_path = f"life/{uuid4().hex}{extension}"
    destination = settings.sugar_upload_path / file_path
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    except OSError as error:
        raise HTTPException(500, '图片保存失败，请稍后重试') from error
    return {'url': f'/uploads/{file_path}'}
