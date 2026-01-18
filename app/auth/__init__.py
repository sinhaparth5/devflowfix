# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Zitadel Authentication Module

This module provides authentication via Zitadel OIDC.
It validates JWT tokens issued by Zitadel and extracts user information.

Structure:
- app/auth/              → Authentication logic (this module)
- app/core/schemas/zitadel.py → Pydantic schemas for API responses
- app/adapters/database/postgres/models.py → UserTable (database model)
"""

from app.auth.zitadel import (
    get_current_user,
    get_current_active_user,
    get_optional_user,
    require_admin,
    ZitadelUser,
    ZitadelAuth,
)
from app.auth.config import ZitadelSettings, get_zitadel_settings

__all__ = [
    # Auth dependencies (use in route handlers)
    "get_current_user",
    "get_current_active_user",
    "get_optional_user",
    "require_admin",
    # Classes
    "ZitadelUser",
    "ZitadelAuth",
    # Config
    "ZitadelSettings",
    "get_zitadel_settings",
]
