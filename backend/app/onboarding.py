"""新手引导的完成记录。

引导本身是纯前端行为（步骤表在 ``frontend/src/composables/onboardingSteps.js``），
服务端只记住「这个账号看到过哪一版」：记在账号上而不是浏览器本地，
换设备或清缓存后不会重复打扰；前端递增 ONBOARDING_VERSION 即可让老用户再看一次新版。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import get_current_user
from .models import User
from .ratelimit import enforce
from .schemas import OnboardingAckRequest, OnboardingStatusOut

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.post("/complete", response_model=OnboardingStatusOut)
def complete_onboarding(
    payload: OnboardingAckRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """记下「已看过第 N 版引导」。只增不减，重复提交幂等。

    刻意不校验服务端是否认识这个版本号：版本号由前端引导内容决定，
    多存一个更大的值只会让用户少看一次旧引导，不会造成越权或数据问题。
    """
    enforce("onboarding-ack", str(user.id), 20, 600)
    if payload.version > (user.onboarding_version or 0):
        user.onboarding_version = payload.version
        db.commit()
        db.refresh(user)
    return OnboardingStatusOut(onboarding_version=user.onboarding_version or 0)
