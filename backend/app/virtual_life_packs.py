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
from .dependencies import get_life_player, get_role_manager
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


def _validate_event_message(message: object, npc_ids: set[str], where: str) -> None:
    # 回复复用消息组校验,显式禁止嵌套选项点。
    if not isinstance(message, dict):
        _fail(f'{where} 消息组必须是对象')
    if 'choice' in message:
        _fail(f'{where} 消息组禁止嵌套选项点 choice')
    speaker = message.get('speaker')
    if not isinstance(speaker, dict) or ('npcId' in speaker) == ('name' in speaker):
        _fail(f'{where} speaker 必须恰好指定 npcId 或 name')
    if not set(speaker).issubset({'npcId', 'name', 'avatar'}):
        _fail(f'{where} speaker 包含未知字段')
    if 'npcId' in speaker and (not isinstance(speaker['npcId'], str) or speaker['npcId'] not in npc_ids):
        _fail(f'{where} speaker 指向未知 NPC')
    if 'name' in speaker and (not isinstance(speaker['name'], str) or not speaker['name']):
        _fail(f'{where} speaker 缺少名字')
    if 'avatar' in speaker and not isinstance(speaker['avatar'], str):
        _fail(f'{where} speaker avatar 必须是字符串')
    lines = message.get('lines')
    if not isinstance(lines, list) or not lines or \
            any(not isinstance(line, str) or not line for line in lines):
        _fail(f'{where} 台词必须是非空句子数组')
    image = message.get('image')
    if image is not None and (not isinstance(image, str) or not image.startswith('/uploads/')):
        _fail(f'{where} 图片必须是 /uploads/ 站内路径')


def _validate_events(events: object, room_ids: set[str], npc_ids: set[str]) -> None:
    if not isinstance(events, list):
        _fail('events 必须是数组')
    event_ids = set()
    for event in events:
        if not isinstance(event, dict):
            _fail('event 必须是对象')
        event_id = event.get('id')
        if not isinstance(event_id, str) or not event_id or event_id in event_ids:
            _fail('event id 缺失或重复')
        event_ids.add(event_id)
        if not isinstance(event.get('roomId'), str) or event['roomId'] not in room_ids:
            _fail(f'事件 {event_id} 指向未知房间')
        for key in ('title', 'icon'):
            if not isinstance(event.get(key), str) or not event[key]:
                _fail(f'事件 {event_id} 的 {key} 必须是非空字符串')
        scripts = event.get('scripts')
        if not isinstance(scripts, list) or len(scripts) != 7:
            _fail(f'事件 {event_id} 的 scripts 必须恰好 7 份')
        for day_index, script in enumerate(scripts, 1):
            where = f'事件 {event_id}/第{day_index}天'
            messages = script.get('messages') if isinstance(script, dict) else None
            if not isinstance(messages, list) or not messages:
                _fail(f'{where} messages 必须是非空数组')
            for message in messages:
                if not isinstance(message, dict) or 'choice' not in message:
                    _validate_event_message(message, npc_ids, where)
                    continue
                if set(message) != {'choice'}:
                    _fail(f'{where} 选项点与消息组必须二选一')
                choice = message['choice']
                options = choice.get('options') if isinstance(choice, dict) else None
                if not isinstance(options, list) or not options:
                    _fail(f'{where} options 必须是非空数组')
                for option in options:
                    if not isinstance(option, dict) or not isinstance(option.get('label'), str) or not option['label']:
                        _fail(f'{where} 存在无文案选项')
                    effects = option.get('effects', {})
                    if not isinstance(effects, dict):
                        _fail(f'{where} 选项 effects 必须是对象')
                    if not set(effects).issubset({'stats', 'bond'}):
                        _fail(f'{where} 选项 effects 只允许 stats,bond,禁止其他键')
                    stats = effects.get('stats', {})
                    if not isinstance(stats, dict) or not set(stats).issubset(STAT_KEYS):
                        _fail(f'{where} 选项包含未知属性')
                    if any(type(value) is not int or not -100 <= value <= 100 for value in stats.values()):
                        _fail(f'{where} 选项属性变化无效')
                    if 'bond' in effects:
                        bond = effects['bond']
                        if not isinstance(bond, dict) or set(bond) != {'npcId', 'value'}:
                            _fail(f'{where} 选项 bond 必须是恰好包含 npcId,value 的对象')
                        if not isinstance(bond['npcId'], str) or bond['npcId'] not in npc_ids:
                            _fail(f'{where} 选项 bond 指向未知 NPC')
                        if type(bond['value']) is not int or not -100 <= bond['value'] <= 100:
                            _fail(f'{where} 选项 bond value 必须是 -100..100 的整数')
                    reply = option.get('reply')
                    if not isinstance(reply, list) or not reply:
                        _fail(f'{where} reply 必须是非空消息组数组')
                    for reply_message in reply:
                        _validate_event_message(reply_message, npc_ids, f'{where}/回复')


def _validate_fallback_replies(replies: object, npc_id: str) -> None:
    where = f'NPC {npc_id} 的 fallbackReplies'
    if not isinstance(replies, list):
        _fail(f'{where} 必须是数组')
    for index, reply in enumerate(replies, 1):
        reply_where = f'{where}/第{index}条'
        if not isinstance(reply, dict):
            _fail(f'{reply_where} 必须是对象')
        if not set(reply).issubset({'text', 'minBond'}):
            _fail(f'{reply_where} 包含未知字段')
        if not isinstance(reply.get('text'), str) or not reply['text']:
            _fail(f'{reply_where} 的 text 必须是非空字符串')
        min_bond = reply.get('minBond', 0)
        if type(min_bond) is not int or not 0 <= min_bond <= 100:
            _fail(f'{reply_where} 的 minBond 必须是 0..100 的整数')


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
        _validate_fallback_replies(npc.get('fallbackReplies', []), npc['id'])

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

    _validate_events(content.get('events', []), room_ids, ids)

    # 初始房间:玩家进入游戏的默认位置;空值(None/空串)由前端自动挑选第一个可加入房间。
    start_room = content.get('startRoomId')
    if start_room is not None and start_room != '':
        if not isinstance(start_room, str) or start_room not in room_ids:
            _fail('startRoomId 必须指向已有房间')

    # 条件结局:列表顺序即优先级,第一个满足全部条件的结局生效;
    # 条件为空的结局恒成立,排在最后充当兜底结局。
    endings = content.get('endings', [])
    if not isinstance(endings, list):
        _fail('endings 必须是数组')
    ending_ids = set()
    for ending in endings:
        if not isinstance(ending, dict):
            _fail('结局必须是对象')
        if not isinstance(ending.get('id'), str) or not ending['id'] or ending['id'] in ending_ids:
            _fail('结局 id 缺失或重复')
        ending_ids.add(ending['id'])
        if not isinstance(ending.get('name'), str) or not ending['name']:
            _fail(f"结局 {ending['id']} 缺少名称")
        if not isinstance(ending.get('text'), str) or not ending['text']:
            _fail(f"结局 {ending['id']} 缺少文案")
        image = ending.get('image')
        if image is not None and (not isinstance(image, str) or not image.startswith('/uploads/')):
            _fail(f"结局 {ending['id']} 图片必须是 /uploads/ 站内路径")
        conditions = ending.get('conditions')
        if conditions is None:
            conditions = {}
        if not isinstance(conditions, dict):
            _fail(f"结局 {ending['id']} 条件必须是对象")
        cond_stats = conditions.get('stats', {})
        if not isinstance(cond_stats, dict) or not set(cond_stats).issubset(STAT_KEYS):
            _fail(f"结局 {ending['id']} 条件包含未知属性")
        if any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 100 for v in cond_stats.values()):
            _fail(f"结局 {ending['id']} 属性条件必须是 0-100 整数")
        cond_bonds = conditions.get('bonds', {})
        if not isinstance(cond_bonds, dict) or not set(cond_bonds).issubset(ids):
            _fail(f"结局 {ending['id']} 条件包含未知 NPC")
        if any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 100 for v in cond_bonds.values()):
            _fail(f"结局 {ending['id']} 好感条件必须是 0-100 整数")

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
    for npc_id, days in dialogue.items():
        # 每个 NPC 的剧本按天编排:1-7 天的数组,超出天数后游戏沿用最后一天的剧本(不循环)。
        if not isinstance(days, list) or not 1 <= len(days) <= 7:
            _fail(f"{npc_id} 的剧本必须是 1-7 天的数组")
        for day_index, script in enumerate(days, 1):
            where = f"{npc_id}/第{day_index}天"
            nodes = script.get('nodes') if isinstance(script, dict) else None
            if not isinstance(nodes, dict) or not nodes:
                _fail(f"{where} 的剧本没有节点")
            if script.get('start') not in nodes:
                _fail(f"{where} 的剧本起点无效")
            for node_id, node in nodes.items():
                lines = node.get('lines')
                if not isinstance(lines, list) or not lines or \
                        any(not isinstance(l, str) or not l for l in lines):
                    _fail(f"{where}/{node_id} 台词必须是非空句子数组")
                image = node.get('image')
                if image is not None and (not isinstance(image, str) or not image.startswith('/uploads/')):
                    _fail(f"{where}/{node_id} 图片必须是 /uploads/ 站内路径")
                choices = node.get('choices')
                if not isinstance(choices, list) or not choices:
                    _fail(f"{where}/{node_id} 缺少选项")
                for choice in choices:
                    if not isinstance(choice.get('label'), str) or not choice['label']:
                        _fail(f"{where}/{node_id} 存在无文案选项")
                    replies = choice.get('replies')
                    if not isinstance(replies, list) or not replies or \
                            any(not isinstance(r, str) or not r for r in replies):
                        _fail(f"{where}/{node_id} 存在无回复选项")
                    reply_image = choice.get('replyImage')
                    if reply_image is not None and (not isinstance(reply_image, str) or not reply_image.startswith('/uploads/')):
                        _fail(f"{where}/{node_id} 回复图片必须是 /uploads/ 站内路径")
                    if choice.get('next') is not None and choice.get('next') not in nodes:
                        _fail(f"{where}/{node_id} 选项跳转到未知节点 {choice.get('next')}")
                    effects = choice.get('effects') or {}
                    if not isinstance(effects, dict):
                        _fail(f"{where}/{node_id} 选项 effects 必须是对象")
                    bond = effects.get('bond', 0)
                    if not isinstance(bond, int) or not 0 <= bond <= 100:
                        _fail(f"{where}/{node_id} 选项好感变化无效")
                    stats = effects.get('stats', {})
                    if not isinstance(stats, dict) or not set(stats).issubset(STAT_KEYS):
                        _fail(f"{where}/{node_id} 选项包含未知属性")
                    if any(not isinstance(v, int) or not -100 <= v <= 100 for v in stats.values()):
                        _fail(f"{where}/{node_id} 选项属性变化无效")

    initial = content.get('initialState')
    if not isinstance(initial, dict):
        _fail('缺少 initialState')
    # 七日制:起始天最多第 6 天,第 7 天开局等于直接结局。
    if not isinstance(initial.get('day'), int) or not 1 <= initial['day'] <= 6:
        _fail('initialState.day 必须是 1-6 的整数')
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
        'eventIds': [event['id'] for event in content.get('events', [])],
        'roomIds': [r['id'] for r in enterable],
        'roomWorlds': {r['id']: world_name[r['worldId']] for r in enterable},
        'dialogueNodes': {npc_id: set().union(*(day['nodes'] for day in days))
                          for npc_id, days in content['dialogue'].items()},
    }


def get_active_pack(db: Session) -> VirtualLifePack:
    pack = db.scalar(select(VirtualLifePack).where(VirtualLifePack.is_active.is_(True)))
    if pack is None:
        raise HTTPException(500, '站点尚未配置虚拟人生内容包')
    return pack


def get_save_rules(db: Session) -> dict:
    pack = get_active_pack(db)
    return derive_save_rules(json.loads(pack.content_json)) | {'packId': pack.id}


def migrate_pack_content(content: dict) -> bool:
    """Upgrade legacy dialogue shapes in place (idempotent):
    {npc: script} -> {npc: [script]}; node.line -> lines[]; choice.reply ->
    replies[]; fill image/replyImage defaults (stage 8a message groups),
    events and NPC fallbackReplies defaults."""
    changed = False
    # 旧 NPC 没有兜底回复,仅补缺省值,不覆盖已有配置。
    npcs = content.get('npcs')
    if isinstance(npcs, list):
        for npc in npcs:
            if isinstance(npc, dict) and 'fallbackReplies' not in npc:
                npc['fallbackReplies'] = []
                changed = True
    # 旧内容包没有房间事件,补空数组且不覆盖已有事件。
    if 'events' not in content:
        content['events'] = []
        changed = True
    dialogue = content.get('dialogue')
    if not isinstance(dialogue, dict):
        return changed
    for npc_id, script in dialogue.items():
        if isinstance(script, dict) and 'nodes' in script:
            dialogue[npc_id] = [script]
            changed = True
    for days in dialogue.values():
        if not isinstance(days, list):
            continue
        for script in days:
            nodes = script.get('nodes') if isinstance(script, dict) else None
            if not isinstance(nodes, dict):
                continue
            for node in nodes.values():
                if not isinstance(node, dict):
                    continue
                if isinstance(node.get('line'), str):
                    node['lines'] = [node.pop('line')]
                    changed = True
                if 'image' not in node:
                    node['image'] = None
                    changed = True
                for choice in node.get('choices') or []:
                    if not isinstance(choice, dict):
                        continue
                    if isinstance(choice.get('reply'), str):
                        choice['replies'] = [choice.pop('reply')]
                        changed = True
                    if 'replyImage' not in choice:
                        choice['replyImage'] = None
                        changed = True
    return changed


def seed_virtual_life_packs(db: Session) -> None:
    """First startup: load bundled JSON seeds; the default pack becomes active.
    Later startups: upgrade older stored content shapes in place."""
    if db.scalar(select(VirtualLifePack.id).limit(1)) is None:
        now = datetime.now(timezone.utc).isoformat()
        for path in sorted(SEED_DIR.glob('*.json')):
            content = json.loads(path.read_text(encoding='utf-8'))
            migrate_pack_content(content)  # 种子可能是旧形状,先归一化再校验
            validate_pack_content(content)
            db.add(VirtualLifePack(
                id=path.stem, name='默认内容包', version=1,
                content_json=json.dumps(content, ensure_ascii=False),
                is_active=path.stem == DEFAULT_PACK_ID, updated_at=now,
            ))
        db.commit()
        return
    changed = False
    for pack in db.scalars(select(VirtualLifePack)):
        content = json.loads(pack.content_json)
        if migrate_pack_content(content):
            validate_pack_content(content)
            pack.content_json = json.dumps(content, ensure_ascii=False)
            changed = True
    if changed:
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
def read_active_pack(user: User = Depends(get_life_player), db: Session = Depends(get_db)):
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
    # 平滑迁移:仍指向旧包的存档,与新包兼容的就地改指(阶段 7;延迟导入避免循环依赖)。
    from .virtual_life import migrate_saves_to_active_pack
    migration = migrate_saves_to_active_pack(db)
    return _detail(pack) | {'saveMigration': migration}


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
