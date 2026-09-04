"""万事屋看板娘「小白」:站内可对话的 AI 助手(集中式大脑)。

- 大脑统一部署在服务器的新 Koishi 实例(koishi-mascot + hds-interlude,含记忆/心理导师人设),
  本站只做转发:post {MASCOT_API_BASE}/mascot/chat { token, user_key, messages }。
- 配置:Settings.mascot_*(.env 对应 MASCOT_API_BASE=大脑网关地址、MASCOT_API_KEY=网关访问 token)。
- 不配置时,/api/mascot/chat 返回 disabled=true,前端显示离线文案,不影响其它功能。
- 会话身份:已登录用户 → 站内 user id(跨端记忆);未登录游客 → guest(共享匿名记忆)。
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .dependencies import get_optional_user
from .models import User

MAX_HISTORY = 20  # 客户端一次最多携带的历史消息条数


class MascotMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2000)


class MascotChatRequest(BaseModel):
    messages: list[MascotMessage] = Field(min_length=1, max_length=MAX_HISTORY)


class MascotChatResponse(BaseModel):
    reply: str = ""
    disabled: bool = False


class MascotHealthResponse(BaseModel):
    enabled: bool = False
    name: str = "小白"


router = APIRouter(prefix="/api/mascot", tags=["看板娘"])


@router.get("/health", response_model=MascotHealthResponse)
def mascot_health() -> MascotHealthResponse:
    return MascotHealthResponse(enabled=bool(settings.mascot_api_key))


@router.post("/chat", response_model=MascotChatResponse)
async def mascot_chat(
    req: MascotChatRequest,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> MascotChatResponse:
    if not settings.mascot_api_key or not settings.mascot_api_base:
        return MascotChatResponse(
            reply="呜…看板娘还没接上大脑呢,店长忘接线了。请稍后再来找我玩~",
            disabled=True,
        )
    # 会话身份:登录用户用站内 id,游客统一 guest
    user_key = str(user.id) if user else "guest"
    payload = {
        "token": settings.mascot_api_key,
        "user_key": user_key,
        "messages": [m.model_dump() for m in req.messages],
    }
    base = settings.mascot_api_base.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=settings.mascot_timeout_seconds) as client:
            resp = await client.post(f"{base}/mascot/chat", json=payload)
            data = resp.json()
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="看板娘暂时走神了,请稍后再试")
        reply = (data.get("reply") or "").strip()
        if not reply:
            return MascotChatResponse(
                reply="呜…我刚刚走神了,什么也没说出来,再问我一次好不好?",
            )
        return MascotChatResponse(reply=reply)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 —— 对用户只暴露友好错误
        import logging

        logging.getLogger("mascot").warning("看板娘调用大脑失败: %s", exc)
        raise HTTPException(status_code=502, detail="看板娘暂时走神了,请稍后再试")
