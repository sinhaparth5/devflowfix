"""API v1 router composition."""

from fastapi import APIRouter

from .analytics import router as analytics_router
from .events import router as events_router
from .incidents import router as incidents_router
from .jobs import router as jobs_router
from .logs import router as logs_router
from .pr_management import router as pr_management_router
from .user_details import router as user_details_router
from .webhook import router as webhook_router


router = APIRouter(prefix="/v1")

router.include_router(incidents_router)
router.include_router(webhook_router)
router.include_router(analytics_router)
router.include_router(pr_management_router)
router.include_router(user_details_router)
router.include_router(logs_router)
router.include_router(jobs_router)
router.include_router(events_router)
