import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.auth.zitadel import (
    ZitadelAuth,
    ZitadelUser,
    get_current_active_analytics_user,
)


@pytest.mark.asyncio
async def test_get_userinfo_deduplicates_concurrent_requests():
    auth = ZitadelAuth(settings=SimpleNamespace(userinfo_uri="https://example.com/userinfo"))

    calls = 0

    async def fake_fetch(token: str):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"sub": "user_123", "email": "user@example.com"}

    auth._fetch_userinfo = fake_fetch

    results = await asyncio.gather(
        auth.get_userinfo("token-123"),
        auth.get_userinfo("token-123"),
        auth.get_userinfo("token-123"),
    )

    assert calls == 1
    assert all(result["sub"] == "user_123" for result in results)


@pytest.mark.asyncio
async def test_get_current_active_analytics_user_uses_cached_snapshot(monkeypatch):
    user = ZitadelUser(sub="user_123", email="user@example.com")
    db = Mock()

    from app.auth import zitadel as zitadel_module

    auth = ZitadelAuth(settings=SimpleNamespace(userinfo_uri="https://example.com/userinfo"))
    auth._active_user_cache["user_123"] = {
        "user_id": "user_123",
        "email": "user@example.com",
        "full_name": "Test User",
        "avatar_url": None,
        "is_active": True,
        "is_verified": True,
        "role": "user",
        "oauth_provider": "zitadel",
        "oauth_id": "user_123",
        "created_at": None,
        "updated_at": None,
        "last_login_at": None,
    }
    monkeypatch.setattr(zitadel_module, "_auth_instance", auth)

    current_user = await get_current_active_analytics_user(user=user, db=db)

    assert current_user["user"].user_id == "user_123"
    assert current_user["db_user"].user_id == "user_123"
    db.query.assert_not_called()
