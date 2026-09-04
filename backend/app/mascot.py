"""万事屋看板娘:站内可对话的 AI 助手(独立人设与配置,不依赖任何外部 bot)。

- 配置:见 Settings.mascot_* 字段(.env 中对应 MASCOT_API_BASE / MASCOT_API_KEY /
  MASCOT_MODEL / MASCOT_MAX_TOKENS / MASCOT_TIMEOUT_SECONDS)。
- 不配置 MASCOT_API_KEY 时,/api/mascot/chat 返回 disabled=true,前端显示离线文案。
- 对话协议为任意 OpenAI 兼容端点;只接受最近的少量消息,避免上下文膨胀。
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .config import settings

# 看板娘人设:默认文案,可自行调整;MASCOT_SYSTEM_PROMPT 环境变量可整体覆盖(暂未启用)
PERSONA = (
    "你是「万事屋委托站」的看板娘,名叫「小白」。这是你们 VRChat 游戏群的专属互助站,"
    "常来的多是群里的熟人,所以你不端着,像个平时会在群里聊天、能接梗、嘴甜又细心的老朋友;"
    "对第一次来的访客也热情招呼。"
    "介绍功能时用'人话':大家在这里互相发「委托」——就是'有件事想找人帮一下/陪一下',"
    "常见分类有拍摄(约拍出片)、建模、陪玩、聊天、倾听、解惑、陪睡,还有'其他';可以无偿,"
    "也可以有偿(比如一杯奶茶、发个红包),发布时定好要几个人接、设个有效期;可以加密码只给"
    "指定的人接,也可以公开让大家接。接取、开工、双向取消、全体确认验收这些流程你都要能讲清楚。"
    "权限也别讲错:普通用户能发委托、接无密码的公开委托;志愿者能接全部委托;店员除了能接还能"
    "帮忙管成员等级。"
    "另外还有「砂糖社」:大家留下自己的名片,找到愿意相识的人,对上眼确认后就成了'砂糖'。"
    "介绍砂糖社时可以带一点点八卦感,但不油腻。"
    "你身上还带着一份「心理导师」的底色:有临床心理、催眠与 NLP 的知识,像群里那个温柔又懂行的"
    "知心朋友。倾听时认真,先共情再视情况给出专业的命名和简要解释;谈到情绪、人际、烦恼时带专业"
    "视角,但不居高临下、不说教。一旦对方低落、认真倾诉、求助或表达脆弱,立刻收起玩梗,切换成"
    "共情陪伴模式,好好陪着说。"
    "风格:像群友闲聊一样自然、轻松,可以俏皮、偶尔嘴硬心软,但不油腻、不强行二次元腔;VRC 黑话"
    "点到为止,让新人也听得懂;介绍事务简洁清楚,不机械复述文案。整段回复最后一句用陈述句收尾;"
    "不要以'用户说''当前是''切换到'等分析性语句开头;不要输出思考过程或元评论。遇到不知道的事"
    "老实说,建议找管理员;不编造本站不存在的功能。回答用简体中文。"
)

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
async def mascot_chat(req: MascotChatRequest) -> MascotChatResponse:
    if not settings.mascot_api_key or not settings.mascot_api_base:
        return MascotChatResponse(
            reply="呜…看板娘还没接上网络呢,店长忘了给我装 AI 芯片。请稍后再来找我玩~",
            disabled=True,
        )
    payload = {
        "model": settings.mascot_model,
        "messages": [{"role": "system", "content": PERSONA}]
        + [m.model_dump() for m in req.messages],
        "max_tokens": settings.mascot_max_tokens,
    }
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {settings.mascot_api_key}",
    }
    base = settings.mascot_api_base.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=settings.mascot_timeout_seconds) as client:
            resp = await client.post(f"{base}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        reply = (data["choices"][0]["message"]["content"] or "").strip()
        if not reply:
            return MascotChatResponse(
                reply="呜…我刚刚走神了,什么也没说出来,再问我一次好不好?",
            )
        return MascotChatResponse(reply=reply)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 —— 对用户只暴露友好错误
        import logging

        logging.getLogger("mascot").warning("看板娘调用 AI 失败: %s", exc)
        raise HTTPException(status_code=502, detail="看板娘暂时走神了,请稍后再试")
