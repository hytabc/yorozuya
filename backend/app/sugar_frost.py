"""One private Sugar Frost save per logged-in user.

No caller-supplied owner id. Revision compare-and-swap prevents stale tabs from
silently overwriting newer saves. This table is independent of other businesses.

Progress is a plain validated snapshot (cleared levels, seen endings/butterflies,
bond values, hint/attempt counters); unlike virtual-life there is no active pack
to validate against, so the shape and size are the only server-side contract.
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
from .dependencies import get_current_user
from .models import User


class SugarFrostSave(Base):
    __tablename__ = "sugar_frost_saves"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Settings(StrictModel):
    reduceMotion: bool = False
    colorBlind: bool = False
    highContrast: bool = False
    fontScale: Literal['small', 'medium', 'large'] = 'medium'


class FrostState(StrictModel):
    schemaVersion: Literal[1] = 1
    cleared: list[str] = Field(default_factory=list, max_length=100)
    endingsSeen: list[str] = Field(default_factory=list, max_length=300)
    butterfliesSeen: list[str] = Field(default_factory=list, max_length=50)
    bond: dict[Literal['Mio', 'Shiori', 'Rin', 'Yu'], int] = Field(default_factory=dict)
    hintsUsed: dict[str, int] = Field(default_factory=dict)
    fails: dict[str, int] = Field(default_factory=dict)
    attempts: dict[str, int] = Field(default_factory=dict)
    chaosCount: int = Field(default=0, ge=0, le=100000)
    lastLevel: str | None = Field(default=None, max_length=20)
    settings: Settings = Field(default_factory=Settings)

    @model_validator(mode='after')
    def check_state(self):
        for field_name, max_len in (('cleared', 40), ('endingsSeen', 60), ('butterfliesSeen', 40)):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f'{field_name} 存在重复项')
            if any(not value or len(value) > max_len for value in values):
                raise ValueError(f'{field_name} 含有非法条目')
        if any(value < -100 or value > 100 for value in self.bond.values()):
            raise ValueError('羁绊值超出范围')
        for mapping in (self.hintsUsed, self.fails, self.attempts):
            for key, value in mapping.items():
                if not key or len(key) > 40 or value < 0 or value > 100000:
                    raise ValueError('计数项非法')
        if len(self.cleared) > len(set(self.cleared)):
            raise ValueError('关卡进度存在重复项')
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 2_000_000:
            raise ValueError('Save exceeds 2 MB')
        return self


class SaveRequest(StrictModel):
    revision: int = Field(ge=0)
    state: FrostState


router = APIRouter(prefix='/api/sugar-frost', tags=['sugar-frost'])


@router.get('/save')
def read_save(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SugarFrostSave, user.id)
    if row is None:
        return {'revision': 0, 'state': None, 'updatedAt': None}
    return {'revision': row.revision, 'state': json.loads(row.state_json), 'updatedAt': row.updated_at}


@router.put('/save')
def write_save(payload: SaveRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    encoded = json.dumps(payload.state.model_dump(), ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()
    revision = payload.revision + 1
    if payload.revision == 0:
        db.add(SugarFrostSave(user_id=user.id, revision=revision, state_json=encoded, updated_at=now))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, '存档已被其他页面更新，请重新载入后继续')
    else:
        result = db.execute(update(SugarFrostSave).where(
            SugarFrostSave.user_id == user.id,
            SugarFrostSave.revision == payload.revision,
        ).values(revision=revision, state_json=encoded, updated_at=now))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, '存档已被其他页面更新，请重新载入后继续')
        db.commit()
    return {'revision': revision, 'updatedAt': now}
