"""House ownership, immutable versions, collision, visits and media regression tests."""
import copy
import hashlib
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main, media, house
from app.config import settings
from app.database import Base, get_db
from app.models import User, UserRole
from app.security import create_access_token


DATA={'gridSize':16,'mount':'floor','palette':[{'key':'wood','label':'木材','color':'#b58b63','editable':True}], 'voxels':[[0,0,0,0],[1,0,0,0]]}
STATE={'schemaVersion':1,'name':'测试小屋','placements':[], 'floor':{'color':'#eee5d5','textureId':None,'mode':'repeat'},'wall':{'color':'#f2eee5','textureId':None,'mode':'repeat'}}


@pytest.fixture()
def env(tmp_path,monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine); factory=sessionmaker(engine,expire_on_commit=False)
    with factory() as db:
        for uid,role,verified in [(1,UserRole.USER,True),(2,UserRole.USER,True),(3,UserRole.USER,False),(4,UserRole.STAFF,True),(5,UserRole.DISCIPLINARIAN,True),(6,UserRole.MASCOT,True)]:
            db.add(User(id=uid,username=f'house{uid}',nickname=f'玩家{uid}',password_hash='unused',email=f'house{uid}@example.com',email_verified=verified,role=role))
        db.add(house.HouseFurniture(id='test-chair',user_id=1,name='小木椅',category='chair',style='原木',version_id='version-one',is_public=True,
                                   published_version_id='version-one',published_name='小木椅',published_category='chair',published_style='原木'))
        db.add(house.HouseVersion(id='version-one',furniture_id='test-chair',data_json=json.dumps(DATA)))
        db.commit()
    def get_test_db():
        with factory() as db: yield db
    previous=main.app.dependency_overrides.copy();main.app.dependency_overrides[get_db]=get_test_db
    monkeypatch.setattr(settings,'sugar_upload_dir',str(tmp_path/'uploads'))
    monkeypatch.setattr(settings,'media_private_dir',str(tmp_path/'private_media'))
    monkeypatch.setattr(settings,'require_email_verification',True)
    headers=lambda uid:{'Authorization':f'Bearer {create_access_token(uid)}'}
    with TestClient(main.app,raise_server_exceptions=True) as client:
        yield client,headers,factory,tmp_path
    main.app.dependency_overrides.clear();main.app.dependency_overrides.update(previous);engine.dispose()


def place(version='version-one',ident='p1',x=0,y=0,z=0,rotation=0,overrides=None):
    return {'id':ident,'versionId':version,'position':{'x':x,'y':y,'z':z},'rotation':rotation,'paletteOverrides':overrides or {}}


def save(client,headers,placements=None,revision=0):
    state=copy.deepcopy(STATE);state['placements']=placements or []
    return client.put('/api/house/room',headers=headers(1),json={'revision':revision,'state':state})


def share(client,headers):
    return client.patch('/api/house/room/share',headers=headers(1),json={'enabled':True}).json()['shareId']


def test_house_page_analytics_accepts_visits_and_dwell(env):
    client, headers, _, _ = env
    payload = {'page_key': 'house', 'session_id': 'house-visitor-session'}
    assert client.post('/api/analytics/page-view', json=payload).is_success
    assert client.post('/api/analytics/page-dwell', json={**payload, 'seconds': 12}).is_success
    report = client.get('/api/operations/analytics', headers=headers(4)).json()
    room = next(page for page in report['pages'] if page['page_key'] == 'house')
    assert room['views'] == 1
    assert room['total_seconds'] == 12


def test_catalog_geometry_palettes_and_assets():
    catalog=house.catalog();assert len(catalog['categories'])==24;assert len(catalog['models'])==120
    public=Path(__file__).resolve().parents[2]/'frontend/public'
    for category in catalog['categories']:
        models=[m for m in catalog['models'] if m['category']==category['id']]
        assert len(models)>=5
        shapes={hashlib.sha256(json.dumps([p[:3] for p in m['voxels']]).encode()).hexdigest() for m in models}
        assert len(shapes)==len(models),category
        for m in models:
            house.VoxelData.model_validate({k:m[k] for k in ['gridSize','mount','palette','voxels']})
            assert any(s['editable'] for s in m['palette'])
            assert (public/m['thumbnail'].lstrip('/')).is_file()
    assert len(catalog['palettes'])==6
    assert len(catalog['textures'])==30
    for t in catalog['textures']: assert (public/t['url'].lstrip('/')).is_file()


def test_seed_does_not_overwrite_versions(env):
    _,_,factory,_=env
    with factory() as db:
        house.seed_house_catalog(db)
        version=db.get(house.HouseVersion,'official-sofa-1-v1');original=version.data_json
        f=db.get(house.HouseFurniture,'official-sofa-1');f.is_visible=False;db.commit()
        house.seed_house_catalog(db)
        assert db.get(house.HouseVersion,version.id).data_json==original
        assert not db.get(house.HouseFurniture,f.id).is_visible


def test_example_layouts_are_valid(env):
    _,_,factory,_=env
    with factory() as db:
        house.seed_house_catalog(db)
        user=db.get(User,1)
        for example in house.catalog()['examples']:
            house.validate_room(db,house.RoomState.model_validate(example['state']),user,{})


def test_one_house_cas_and_account_isolation(env):
    c,h,_,_=env
    assert c.get('/api/house/room').status_code==401
    assert save(c,h,[place()]).status_code==200
    assert save(c,h,[],revision=0).status_code==409
    assert c.get('/api/house/room',headers=h(1)).json()['revision']==1
    assert c.get('/api/house/room',headers=h(2)).json()['state']['placements']==[]
    assert save(c,h,[place()],revision=1).json()['revision']==2


@pytest.mark.parametrize('placement,status',[
    (place(x=255),422),(place(z=128),422),(place(rotation=45),422),
    (place(version='missing'),422),(place(overrides={'wood':'red'}),422),
    (place(overrides={'screen':'#ffffff'}),422),(place(x=1.5),422),
])
def test_invalid_room(env,placement,status):
    c,h,_,_=env;assert save(c,h,[placement]).status_code==status


def test_collision_touching_rotation_and_stacking(env):
    c,h,_,_=env
    assert save(c,h,[place(),place(ident='p2',x=1)]).status_code==422
    assert save(c,h,[place(),place(ident='p2',x=2),place(ident='p3',z=1),place(ident='p4',y=3,rotation=90)]).status_code==200


def test_readonly_sharing_and_rotation_of_link(env):
    c,h,_,_=env;assert save(c,h,[place(overrides={'wood':'#9eafa0'})]).status_code==200
    sid=share(c,h);assert c.get('/api/house/visit/'+sid).status_code==401
    data=c.get('/api/house/visit/'+sid,headers=h(2)).json()
    assert data['state']['placements'][0]['paletteOverrides']=={'wood':'#9eafa0'}
    assert 'email' not in data['owner'] and 'token' not in json.dumps(data)
    assert c.put('/api/house/visit/'+sid,json={'state':STATE}).status_code==405
    assert save(c,h,[],revision=1).status_code==200
    assert len(c.get('/api/house/visit/'+sid,headers=h(2)).json()['state']['placements'])==1
    c.patch('/api/house/room/share',headers=h(1),json={'enabled':True,'revision':2})
    assert c.get('/api/house/visit/'+sid,headers=h(2)).json()['state']['placements']==[]
    c.patch('/api/house/room/share',headers=h(1),json={'enabled':False})
    assert c.get('/api/house/visit/'+sid,headers=h(2)).status_code==404
    assert share(c,h)!=sid


def test_private_version_cannot_be_borrowed(env):
    c,h,factory,_=env
    with factory() as db: f=db.get(house.HouseFurniture,'test-chair');f.is_public=False;db.commit()
    assert c.get('/api/house/versions/version-one',headers=h(2)).status_code==404
    state=copy.deepcopy(STATE);state['placements']=[place()]
    assert c.put('/api/house/room',headers=h(2),json={'revision':0,'state':state}).status_code==403
    assert save(c,h,[place()]).status_code==200
    assert c.get('/api/house/visit/'+share(c,h),headers=h(2)).json()['assets']['version-one']['data']==DATA


def test_furniture_versions_publish_and_delete_preserve_placement(env):
    c,h,_,_=env;save(c,h,[place()]);sid=share(c,h)
    edited=copy.deepcopy(DATA);edited['voxels'].append([2,0,0,0])
    payload={'revision':1,'name':'新版木椅','category':'chair','style':'原木','data':edited}
    updated=c.put('/api/house/furniture/test-chair',headers=h(1),json=payload)
    assert updated.status_code==200
    assert c.put('/api/house/furniture/test-chair',headers=h(1),json=payload).status_code==409
    assert c.put('/api/house/furniture/test-chair',headers=h(2),json={**payload,'revision':2}).status_code==403
    c.patch('/api/house/furniture/test-chair/publish',headers=h(1),json={'enabled':False})
    assert c.get('/api/house/visit/'+sid,headers=h(2)).json()['assets']['version-one']['data']==DATA
    c.delete('/api/house/furniture/test-chair',headers=h(1))
    assert save(c,h,[place()],revision=1).status_code==200
    assert c.get('/api/house/visit/'+sid,headers=h(2)).json()['assets']['version-one']['data']==DATA
    assert c.get('/api/house/versions/'+updated.json()['versionId']).status_code==404


def test_like_idempotency_comments_and_permissions(env):
    c,h,_,_=env;save(c,h);sid=share(c,h);base='/api/house/visit/'+sid
    assert c.put(base+'/like').status_code==401
    for _ in range(2): assert c.put(base+'/like',headers=h(2)).json()['likeCount']==1
    assert c.delete(base+'/like',headers=h(2)).json()['likeCount']==0
    assert c.post(base+'/comments',headers=h(2),json={'content':'  '}).status_code==422
    reply=c.post(base+'/comments',headers=h(2),json={'content':'<script>这是纯文本</script>'});assert reply.status_code==201
    cid=reply.json()['id']
    assert c.get(base+'/comments',headers=h(1)).json()['items'][0]['canDelete']
    assert c.get(base+'/comments').status_code==401
    assert not c.get(base+'/comments',headers=h(6)).json()['items'][0]['canDelete']
    assert c.delete('/api/house/comments/'+str(cid),headers=h(6)).status_code==403
    assert c.delete('/api/house/comments/'+str(cid),headers=h(1)).status_code==204
    assert c.get(base+'/comments',headers=h(2)).json()['total']==0


def test_email_gate_and_moderation(env):
    c,h,_,_=env
    assert c.put('/api/house/room',headers=h(3),json={'revision':0,'state':STATE}).status_code==403
    save(c,h,[place()]);sid=share(c,h)
    for uid in (2,6): assert c.get('/api/admin/house/rooms',headers=h(uid)).status_code==403
    assert c.patch('/api/admin/house/furniture/test-chair',headers=h(5),json={'is_visible':False}).status_code==200
    assert c.get('/api/house/visit/'+sid,headers=h(2)).json()['state']['placements']==[]
    assert c.get('/api/house/room',headers=h(1)).json()['assets']['version-one']['furniture']['isVisible'] is False
    roomid=c.get('/api/admin/house/rooms',headers=h(4)).json()['items'][0]['id']
    c.patch('/api/admin/house/rooms/'+roomid,headers=h(4),json={'is_visible':False})
    assert c.get('/api/house/visit/'+sid,headers=h(2)).status_code==404
    assert c.get('/api/admin/house/rooms/'+roomid+'/preview',headers=h(5)).status_code==200
    assert c.patch('/api/house/room/share',headers=h(1),json={'enabled':True}).status_code==403


def test_texture_private_approval_retraction_and_delete(env):
    c,h,factory,tmp=env;img=Image.new('RGB',(16,16),'#83a08a');buf=io.BytesIO();img.save(buf,format='PNG')
    texture=c.post('/api/house/textures',headers=h(1),files={'file':('墙纸.png',buf.getvalue(),'image/png')}).json()
    assert texture['url'].startswith('/api/media/')
    state=copy.deepcopy(STATE);state['wall']['textureId']=texture['id']
    assert c.put('/api/house/room',headers=h(1),json={'revision':0,'state':state}).status_code==200
    sid=share(c,h);visit=c.get('/api/house/visit/'+sid,headers=h(2)).json()
    assert not visit['textureUrls'] and visit['state']['wall']['textureId'] is None
    assert c.get('/api/house/textures',headers=h(2)).json()==[]
    assert c.delete('/api/house/textures/'+str(texture['recordId']),headers=h(2)).status_code==403
    with factory() as db: key=db.get(house.HouseTexture,texture['recordId']).file_path
    assert c.get('/uploads/'+key).status_code==404
    path='/api/admin/house/textures/'+str(texture['recordId'])
    assert c.patch(path,headers=h(4),json={'is_visible':True}).status_code==200
    assert c.get('/uploads/'+key).status_code==200
    assert c.get('/api/house/visit/'+sid,headers=h(2)).json()['textureUrls'][texture['id']]=='/uploads/'+key
    assert c.patch(path,headers=h(4),json={'is_visible':False}).status_code==200
    assert c.get('/uploads/'+key).status_code==404
    assert not c.get('/api/house/visit/'+sid,headers=h(2)).json()['textureUrls']
    assert c.delete('/api/house/textures/'+str(texture['recordId']),headers=h(1)).status_code==204
    assert c.get(texture['url']).status_code==404


def test_texture_move_failure_does_not_publish(env,monkeypatch):
    c,h,factory,_=env
    with factory() as db:
        db.add(house.HouseTexture(user_id=1,name='测试',file_path='house/test.png'));db.commit()
    from fastapi import HTTPException
    def fail(*args,**kwargs): raise HTTPException(503,'测试磁盘失败')
    monkeypatch.setattr(media,'place_media',fail)
    assert c.patch('/api/admin/house/textures/1',headers=h(4),json={'is_visible':True}).status_code==503
    with factory() as db: assert not db.get(house.HouseTexture,1).is_visible


@pytest.mark.parametrize('change',[
    {'voxels':[[16,0,0,0]]},{'voxels':[[0,0,0,1]]},{'voxels':[[0,0,0,0],[0,0,0,0]]},
    {'voxels':[[True,0,0,0]]},{'gridSize':128},{'palette':[{'key':'bad','label':'坏色','color':'red','editable':True}]},
])
def test_furniture_validation(env,change):
    c,h,_,_=env
    payload={'revision':0,'name':'新家具','category':'chair','data':{**DATA,**change}}
    assert c.put('/api/house/furniture/custom-new',headers=h(1),json=payload).status_code==422


def test_legacy_64_grid_is_preserved_but_new_crafts_are_bounded(env):
    c,h,factory,_=env;large={**DATA,'gridSize':64,'voxels':[[x,y,z,0] for x in range(64) for y in range(64) for z in range(64)]}
    with factory() as db:
        db.add(house.HouseFurniture(id='legacy64',user_id=1,name='旧家具',category='deco',style='自制',version_id='legacy-v1'))
        db.add(house.HouseVersion(id='legacy-v1',furniture_id='legacy64',data_json=json.dumps(large)));db.commit()
    assert len(c.get('/api/house/versions/legacy-v1',headers=h(1)).json()['data']['voxels'])==262144
    res=c.put('/api/house/furniture/full64',headers=h(1),json={'revision':0,'name':'64立方','category':'deco','data':large})
    assert res.status_code==422
    res=c.put('/api/house/furniture/legacy64',headers=h(1),json={'revision':1,'name':'旧家具改色','category':'deco','data':large})
    assert res.status_code==200


def test_pagination_creator_and_unknown_fields(env):
    c,h,_,_=env
    listing=c.get('/api/house/furniture?page_size=1').json();assert listing['page_size']==1 and listing['total']==1
    assert c.get('/api/house/furniture?page_size=51').status_code==422
    assert c.get('/api/house/users/1').json()['furniture']['items'][0]['id']=='test-chair'
    assert c.put('/api/house/room',headers=h(1),json={'revision':0,'state':STATE,'user_id':2}).status_code==422


def test_multimaterial_publish_snapshot_favorite_and_independent_copy(env):
    c,h,_,_=env
    materials=['wood','metal','glass','plastic','fabric','stone','ceramic','emissive']
    data={**DATA,'palette':[{'key':f'm{i}','label':m,'material':m,'color':f'#{i+1:06x}','editable':True} for i,m in enumerate(materials)],
          'voxels':[[i,0,0,i] for i in range(8)]}
    payload={'revision':0,'name':'多材质拼豆','category':'deco','data':data}
    created=c.put('/api/house/furniture/beans',headers=h(1),json=payload).json()
    original=created['versionId']
    assert c.get('/api/house/versions/'+original,headers=h(2)).status_code==404
    assert c.patch('/api/house/furniture/beans/publish',headers=h(2),json={'enabled':True}).status_code==403
    assert c.patch('/api/house/furniture/beans/publish',headers=h(1),json={'enabled':True,'revision':1}).status_code==200
    assert c.get('/api/house/versions/'+original,headers=h(2)).json()['data']==data
    for _ in range(2): assert c.put('/api/house/furniture/beans/favorite',headers=h(2)).json()['favorited']
    assert c.put('/api/house/furniture/beans/favorite').status_code==401
    favorites=c.get('/api/house/furniture?favorites=true',headers=h(2)).json()
    assert favorites['total']==1 and favorites['items'][0]['favorited']
    assert c.get('/api/house/furniture?favorites=true',headers=h(1)).json()['total']==0
    copied=c.post('/api/house/furniture/beans/copy',headers=h(2),json={}).json()
    assert copied['creatorId']==2 and not copied['isPublic'] and copied['versionId']!=original
    assert c.get('/api/house/versions/'+copied['versionId'],headers=h(2)).json()['data']==data
    modified=copy.deepcopy(data);modified['palette'][0]['color']='#abcdef'
    updated=c.put('/api/house/furniture/beans',headers=h(1),json={**payload,'revision':1,'name':'私人草稿名称','data':modified}).json()
    public=c.get('/api/house/furniture?search=多材质拼豆').json()['items'][0]
    assert public['name']=='多材质拼豆' and public['versionId']==original
    assert not c.get('/api/house/furniture?search=私人草稿名称').json()['items']
    owner_preview=c.get('/api/house/versions/'+original,headers=h(1)).json()['furniture']
    assert owner_preview['name']=='多材质拼豆' and owner_preview['draftVersionId']==updated['versionId']
    assert c.get('/api/house/versions/'+updated['versionId'],headers=h(2)).status_code==404
    assert c.post('/api/house/furniture/beans/copy',headers=h(2),json={'versionId':updated['versionId']}).status_code==404
    assert c.patch('/api/house/furniture/beans/publish',headers=h(1),json={'enabled':True,'revision':1}).status_code==409
    assert c.patch('/api/house/furniture/beans/publish',headers=h(1),json={'enabled':True,'revision':2}).status_code==200
    assert c.get('/api/house/versions/'+original,headers=h(2)).status_code==404
    assert c.get('/api/house/versions/'+updated['versionId'],headers=h(2)).json()['data']==modified
    assert c.get('/api/house/versions/'+copied['versionId'],headers=h(2)).json()['data']==data
    assert c.patch('/api/house/furniture/beans/publish',headers=h(1),json={'enabled':False}).status_code==200
    assert c.get('/api/house/furniture?favorites=true',headers=h(2)).json()['total']==0
    assert c.post('/api/house/furniture/beans/copy',headers=h(2),json={}).status_code==404
    c.delete('/api/house/furniture/beans',headers=h(1))
    assert c.get('/api/house/versions/'+copied['versionId'],headers=h(2)).json()['data']==data
    assert c.delete('/api/house/furniture/beans/favorite',headers=h(2)).json()['favorited'] is False


def test_visit_directory_drafts_publish_cas_and_retraction(env):
    c,h,_,_=env
    assert c.get('/api/house/rooms').status_code==401
    save(c,h,[place()])
    assert c.get('/api/house/rooms',headers=h(2)).json()['total']==0
    sid=share(c,h)
    published=c.get('/api/house/visit/'+sid,headers=h(2)).json()
    listing=c.get('/api/house/rooms?page_size=1',headers=h(2)).json()
    assert listing['total']==1 and listing['items'][0]['name']==STATE['name']
    assert 'email' not in listing['items'][0]['owner']
    state={**STATE,'name':'未发布的秘密装修','placements':[place(x=40,z=12)]}
    assert c.put('/api/house/room',headers=h(1),json={'revision':1,'state':state}).status_code==200
    assert c.get('/api/house/visit/'+sid,headers=h(2)).json()['state']==published['state']
    assert c.get('/api/house/rooms',headers=h(2)).json()['items'][0]['name']==STATE['name']
    assert c.patch('/api/house/room/share',headers=h(1),json={'enabled':True,'revision':1}).status_code==409
    assert c.patch('/api/house/room/share',headers=h(1),json={'enabled':True,'revision':2}).json()['shareId']==sid
    assert c.get('/api/house/visit/'+sid,headers=h(2)).json()['state']['name']==state['name']
    c.patch('/api/house/room/share',headers=h(1),json={'enabled':False})
    assert c.get('/api/house/visit/'+sid,headers=h(2)).status_code==404
    assert c.get('/api/house/rooms',headers=h(2)).json()['total']==0
    assert c.get('/api/house/room',headers=h(1)).json()['state']['name']==state['name']


def test_private_furniture_metadata_in_visit_is_frozen(env):
    c,h,factory,_=env
    with factory() as db: db.get(house.HouseFurniture,'test-chair').is_public=False;db.commit()
    save(c,h,[place()]);sid=share(c,h)
    payload={'revision':1,'name':'私人新名称','category':'deco','data':DATA}
    assert c.put('/api/house/furniture/test-chair',headers=h(1),json=payload).status_code==200
    asset=c.get('/api/house/visit/'+sid,headers=h(2)).json()['assets']['version-one']
    assert asset['furniture']['name']=='小木椅' and asset['data']==DATA


@pytest.mark.parametrize('change',[
    {'gridSize':64},
    {'gridSize':32,'voxels':[[x,y,z,0] for x in range(32) for y in range(32) for z in range(9)]},
    {'palette':[{'key':f'p{i}','label':'组合','color':'#ffffff','editable':True} for i in range(65)]},
    {'palette':[{'key':'bad','label':'未知','color':'#ffffff','editable':True,'material':'unknown'}]},
])
def test_craft_limits_and_unknown_material(env,change):
    c,h,_,_=env
    assert c.put('/api/house/furniture/over-limit',headers=h(1),json={'revision':0,'name':'超限','category':'deco','data':{**DATA,**change}}).status_code==422


def test_scaled_collision_and_room_bounds(env):
    c,h,_,_=env
    assert save(c,h,[{**place(),'scale':.5},place(ident='p2',x=1)]).status_code==200
    assert save(c,h,[{**place(),'scale':2},place(ident='p2',x=3)],revision=1).status_code==422
    assert save(c,h,[{**place(x=253),'scale':2}],revision=1).status_code==422
    assert save(c,h,[{**place(),'scale':.5},place(ident='p2',z=1)],revision=1).status_code==200


def test_house_sqlite_upgrade_keeps_previous_public_versions(monkeypatch):
    from sqlalchemy import text
    engine=create_engine('sqlite://',poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE house_rooms (id TEXT PRIMARY KEY, state_json TEXT, share_id TEXT, revision INTEGER, updated_at TEXT)'))
        conn.execute(text('CREATE TABLE house_furniture (id TEXT PRIMARY KEY, version_id TEXT, name TEXT, category TEXT, style TEXT, is_public INTEGER, updated_at TEXT)'))
        conn.execute(text('INSERT INTO house_rooms VALUES (:id,:state,:share,3,:date)'),{'id':'old','state':json.dumps(STATE),'share':'old-share','date':'2026-10-01'})
        conn.execute(text("INSERT INTO house_furniture VALUES ('old','old-version','旧家具','chair','原木',1,'2026-10-01')"))
    monkeypatch.setattr(main,'engine',engine)
    main.migrate_schema()
    with engine.begin() as conn:
        conn.execute(text("UPDATE house_rooms SET state_json='{}'"))
        conn.execute(text("UPDATE house_furniture SET version_id='new-version', name='草稿'"))
    main.migrate_schema()
    with engine.connect() as conn:
        r=conn.execute(text('SELECT published_state_json,published_revision FROM house_rooms')).one()
        assert json.loads(r[0])==STATE and r[1]==3
        f=conn.execute(text('SELECT published_version_id,published_name FROM house_furniture')).one()
        assert f==('old-version','旧家具')
    engine.dispose()
