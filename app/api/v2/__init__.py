# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
API v2 Router

New API version with OAuth-based integrations and repository management.
"""

from fastapi import APIRouter

from .oauth import router as oauth_router
from .repositories import router as repositories_router
from .workflows import router as workflows_router
from .prs import router as prs_router
from .analytics import router as analytics_router

# Create v2 API router
router = APIRouter(prefix="/v2", tags=["API v2"])

# Include sub-routers
router.include_router(oauth_router)
router.include_router(repositories_router)
router.include_router(workflows_router)
router.include_router(prs_router)
router.include_router(analytics_router)

# Future routers will be added here:
# router.include_router(integrations_router)
