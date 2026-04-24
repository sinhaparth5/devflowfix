# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Repository Management API Endpoints.

This module now acts as the composition layer for repository connection,
GitLab integration, and GitHub sync routes.
"""

from fastapi import APIRouter

from app.api.v2.repository_connection_routes import router as connection_router
from app.api.v2.repository_gitlab_routes import router as gitlab_router
from app.api.v2.repository_sync_routes import router as sync_router

router = APIRouter(prefix="/repositories", tags=["Repositories"])

router.include_router(connection_router)
router.include_router(gitlab_router)
router.include_router(sync_router)
