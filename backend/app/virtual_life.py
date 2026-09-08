"""One private virtual-life save per authorized player.

No caller-supplied owner id. Revision compare-and-swap prevents stale tabs from
silently overwriting newer saves. This table is independent of other businesses.

Save schema: v1 states (legacy, no packId) are upgraded to v2 on write —
schemaVersion becomes 2 and packId is filled with the active pack. v2 states
must declare the site's active pack id. NPC / room / action whitelists are
derived from the ACTIVE pack stored in the database (virtual_life_packs).
"""
from datetime import datetime, timezone
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Integer, Text, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_life_player
from .models import User
from .virtual_life_packs import get_save_rules


class VirtualLifeSave(Base):
    __tablename__ = "virtual_life_saves"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Stats(StrictModel):
    mood: int = Field(ge=0, le=100)
    energy: int = Field(ge=0, le=100)
    social: int = Field(ge=0, le=100)
    explore: int = Field(ge=0, le=100)


class Message(StrictModel):
    from_: Literal['npc', 'player'] = Field(alias='from')
    text: str = Field(max_length=4000)
    day: int = Field(ge=1)
    time: str = Field(max_length=20)
    # stage 8a: optional site-local image attached to the message.
    image: str | None = Field(default=None, max_length=300)


class Diary(StrictModel):
    day: int = Field(ge=1)
    text: str = Field(max_length=4000)
    mood: str = Field(max_length=100)


class Npc(StrictModel):
    id: str = Field(max_length=50)
    name: str = Field(max_length=100)
    role: str = Field(max_length=100)
    avatar: str = Field(max_length=300)
    status: str = Field(max_length=200)
    bond: int = Field(ge=0, le=100)


class EventProgress(StrictModel):
    day: int = Field(ge=1)
    done: list[str]


class GameState(StrictModel):
    schemaVersion: Literal[1, 2]
    # v2 declares its content pack; v1 (legacy) must omit it.
    packId: str | None = Field(default=None, max_length=100)
    day: int = Field(ge=1)
    stats: Stats
    currentWorld: str = Field(min_length=1, max_length=100)
    unlockedWorlds: int = Field(ge=0)
    currentNpcId: str
    npcs: list[Npc] = Field(min_length=1, max_length=100)
    conversations: dict[str, list[Message]]
    diary: list[Diary]
    completed: dict[str, bool]
    tags: list[str] = Field(max_length=30)
    currentRoomId: str | None = None
    friendIds: list[str] = Field(default_factory=list)
    interactedNpcIds: list[str] | None = None
    # 旧存档反序列化时补房间事件进度。
    eventProgress: EventProgress | None = None
    # game day -> NPC -> action id -> rewarded; omitted in earlier v1 saves.
    actionLedger: dict[str, dict[str, dict[str, Literal[True]]]] = Field(default_factory=dict)
    # NPC -> current dialogue node id (node-graph engine, stage 4c); absent in older saves.
    dialogueNodes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def check_state(self):
        """Pack-independent structural checks; whitelists live in validate_state_against_pack."""
        if self.eventProgress is None:
            self.eventProgress = EventProgress(day=1, done=[])
        if self.interactedNpcIds is None:
            self.interactedNpcIds = [npc_id for npc_id, messages in self.conversations.items()
                                     if any(m.from_ == 'player' for m in messages)]
        if len(set(self.friendIds)) != len(self.friendIds) or len(set(self.interactedNpcIds)) != len(self.interactedNpcIds):
            raise ValueError('Duplicate social identity')
        if not set(self.friendIds).issubset(self.interactedNpcIds):
            raise ValueError('Friend requires prior interaction')
        if any(n.bond < 10 for n in self.npcs if n.id in self.friendIds):
            raise ValueError('Friend requires affection 10')
        for game_day in self.actionLedger:
            if not game_day.isascii() or not game_day.isdecimal() or str(int(game_day)) != game_day or not 1 <= int(game_day) <= self.day:
                raise ValueError('Invalid action reward game day')
        if len(json.dumps(self.model_dump(by_alias=True), ensure_ascii=False).encode()) > 2_000_000:
            raise ValueError('Save exceeds 2 MB')
        return self


def validate_state_against_pack(state: GameState, rules: dict) -> None:
    ids = rules['npcIds']
    if [n.id for n in state.npcs] != ids or state.currentNpcId not in ids:
        raise ValueError('Invalid NPC identity')
    if set(state.conversations) != set(ids) or not set(state.completed).issubset(ids):
        raise ValueError('Invalid conversation/progression owner')
    if not set(state.interactedNpcIds).issubset(ids):
        raise ValueError('Invalid interacted NPC')
    if not set(state.friendIds).issubset(ids):
        raise ValueError('Invalid friend NPC')
    room_world = rules['roomWorlds']
    if state.currentRoomId and (state.currentRoomId not in room_world or
                                state.currentWorld.removesuffix(' · 黄昏') != room_world[state.currentRoomId]):
        raise ValueError('Room and world mismatch')
    action_ids = set(rules['actionIds'])
    for rewards in state.actionLedger.values():
        if not set(rewards).issubset(ids):
            raise ValueError('Invalid action reward NPC')
        for actions in rewards.values():
            if not set(actions).issubset(action_ids):
                raise ValueError('Invalid action reward id')
    dialogue_nodes = rules['dialogueNodes']
    if not set(state.dialogueNodes).issubset(ids):
        raise ValueError('Invalid dialogue progress NPC')
    for npc_id, node_id in state.dialogueNodes.items():
        if node_id not in dialogue_nodes[npc_id]:
            raise ValueError('Invalid dialogue node')
    # 内容包删除事件后宽容清理旧进度,保留其余事件及原有顺序。
    event_ids = set(rules['eventIds'])
    state.eventProgress.done = [event_id for event_id in state.eventProgress.done if event_id in event_ids]


class SaveRequest(StrictModel):
    revision: int = Field(ge=0)
    state: GameState


router = APIRouter(prefix='/api/virtual-life', tags=['virtual-life'])


@router.get('/save')
def read_save(user: User = Depends(get_life_player), db: Session = Depends(get_db)):
    row = db.get(VirtualLifeSave, user.id)
    if row is None:
        return {'revision': 0, 'state': None, 'updatedAt': None}
    return {'revision': row.revision, 'state': json.loads(row.state_json), 'updatedAt': row.updated_at}


@router.put('/save')
def write_save(payload: SaveRequest, user: User = Depends(get_life_player), db: Session = Depends(get_db)):
    rules = get_save_rules(db)
    if payload.state.schemaVersion == 2:
        if payload.state.packId != rules['packId']:
            raise HTTPException(422, '存档内容包与站点配置不一致')
    elif payload.state.packId is not None:
        raise HTTPException(422, '旧版存档不能声明内容包')
    try:
        validate_state_against_pack(payload.state, rules)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    # Legacy v1 saves are upgraded to the active pack on write.
    payload.state.schemaVersion = 2
    payload.state.packId = rules['packId']
    encoded = json.dumps(payload.state.model_dump(by_alias=True), ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()
    revision = payload.revision + 1
    if payload.revision == 0:
        db.add(VirtualLifeSave(user_id=user.id, revision=revision, state_json=encoded, updated_at=now))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, '存档已被其他页面更新，请重新载入后继续')
    else:
        result = db.execute(update(VirtualLifeSave).where(
            VirtualLifeSave.user_id == user.id,
            VirtualLifeSave.revision == payload.revision,
        ).values(revision=revision, state_json=encoded, updated_at=now))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, '存档已被其他页面更新，请重新载入后继续')
        db.commit()
    return {'revision': revision, 'updatedAt': now}


def migrate_saves_to_active_pack(db: Session) -> dict:
    """Pack switch follow-up: repoint compatible saves to the active pack (stage 7).

    Every stored save is re-validated against the NEW active pack's rules;
    compatible ones get packId (and v1→v2 schema) rewritten in place with the
    revision untouched, so the client compare-and-swap keeps working and the
    next load simply succeeds. Incompatible saves are left alone — their
    owners keep the graceful pack-mismatch error until a pack that fits them
    becomes active again.
    """
    rules = get_save_rules(db)
    migrated = skipped = 0
    for row in db.scalars(select(VirtualLifeSave)).all():
        state = json.loads(row.state_json)
        if state.get('schemaVersion') == 2 and state.get('packId') == rules['packId']:
            continue
        candidate = dict(state)
        candidate['schemaVersion'] = 2
        candidate['packId'] = rules['packId']
        try:
            parsed = GameState.model_validate(candidate)
            validate_state_against_pack(parsed, rules)
        except ValueError:  # pydantic ValidationError 也是 ValueError 的子类
            skipped += 1
            continue
        row.state_json = json.dumps(parsed.model_dump(by_alias=True), ensure_ascii=False)
        migrated += 1
    if migrated:
        db.commit()
    return {'migrated': migrated, 'skipped': skipped}
