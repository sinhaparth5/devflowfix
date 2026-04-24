"""API package."""

from fastapi import APIRouter

from .v1 import router as v1_router
from .v2 import router as v2_router


router = APIRouter(prefix="/api")
router.include_router(v1_router)
router.include_router(v2_router)

__all__ = ["router", "v1_router", "v2_router"]
