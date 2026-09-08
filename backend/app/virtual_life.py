"""One private virtual-life save per authenticated administrator.

No caller-supplied owner id. Revision compare-and-swap prevents stale tabs from
silently overwriting newer saves. This table is independent of other businesses.

Save schema: v1 states (legacy, no packId) are upgraded to v2 on write —
schemaVersion becomes 2 and packId is filled with the active pack. v2 states
must declare the site's active pack id. NPC / room / action whitelists come
from the registered content pack (see life_pack_registry), not from code.
"""
from datetime import datetime, timezone
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Integer, Text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_role_manager
from .life_pack_registry import ACTIVE_LIFE_PACK
from .models import User


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
    # game day -> NPC -> action id -> rewarded; omitted in earlier v1 saves.
    actionLedger: dict[str, dict[str, dict[str, Literal[True]]]] = Field(default_factory=dict)

    @model_validator(mode='after')
    def check_state(self):
        pack = ACTIVE_LIFE_PACK
        ids = pack['npcIds']
        if self.schemaVersion == 2:
            if self.packId != pack['id']:
                raise ValueError('Save content pack mismatch')
        elif self.packId is not None:
            raise ValueError('Legacy save cannot declare a content pack')
        if [n.id for n in self.npcs] != ids or self.currentNpcId not in ids:
            raise ValueError('Invalid NPC identity')
        if set(self.conversations) != set(ids) or not set(self.completed).issubset(ids):
            raise ValueError('Invalid conversation/progression owner')
        if self.interactedNpcIds is None:
            self.interactedNpcIds = [npc_id for npc_id in ids if any(m.from_ == 'player' for m in self.conversations[npc_id])]
        if not set(self.interactedNpcIds).issubset(ids):
            raise ValueError('Invalid interacted NPC')
        if not set(self.friendIds).issubset(ids):
            raise ValueError('Invalid friend NPC')
        if len(set(self.friendIds)) != len(self.friendIds) or len(set(self.interactedNpcIds)) != len(self.interactedNpcIds):
            raise ValueError('Duplicate social identity')
        if not set(self.friendIds).issubset(self.interactedNpcIds):
            raise ValueError('Friend requires prior interaction')
        if any(n.bond < 10 for n in self.npcs if n.id in self.friendIds):
            raise ValueError('Friend requires affection 10')
        room_world = pack['roomWorlds']
        if self.currentRoomId and (self.currentRoomId not in room_world or
                                   self.currentWorld.removesuffix(' · 黄昏') != room_world[self.currentRoomId]):
            raise ValueError('Room and world mismatch')
        action_ids = set(pack['actionIds'])
        for game_day, rewards in self.actionLedger.items():
            if not game_day.isascii() or not game_day.isdecimal() or str(int(game_day)) != game_day or not 1 <= int(game_day) <= self.day:
                raise ValueError('Invalid action reward game day')
            if not set(rewards).issubset(ids):
                raise ValueError('Invalid action reward NPC')
            for actions in rewards.values():
                if not set(actions).issubset(action_ids):
                    raise ValueError('Invalid action reward id')
        # Legacy v1 saves are upgraded to the active pack on write.
        self.schemaVersion = 2
        self.packId = pack['id']
        if len(json.dumps(self.model_dump(by_alias=True), ensure_ascii=False).encode()) > 2_000_000:
            raise ValueError('Save exceeds 2 MB')
        return self


class SaveRequest(StrictModel):
    revision: int = Field(ge=0)
    state: GameState


router = APIRouter(prefix='/api/virtual-life', tags=['virtual-life'])


@router.get('/save')
def read_save(user: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    row = db.get(VirtualLifeSave, user.id)
    if row is None:
        return {'revision': 0, 'state': None, 'updatedAt': None}
    return {'revision': row.revision, 'state': json.loads(row.state_json), 'updatedAt': row.updated_at}


@router.put('/save')
def write_save(payload: SaveRequest, user: User = Depends(get_role_manager), db: Session = Depends(get_db)):
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
