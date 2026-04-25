import pytest

from app.adapters.external.github.client import GitHubClient
from app.core.config import Settings


@pytest.mark.asyncio
async def test_github_client_uses_top_level_settings_token() -> None:
    client = GitHubClient(settings=Settings(github_token="settings-token"), enable_cache=False)

    try:
        assert client.token == "settings-token"
        assert client.client.headers["Authorization"] == "Bearer settings-token"
    finally:
        await client.client.aclose()


@pytest.mark.asyncio
async def test_github_client_explicit_token_overrides_settings() -> None:
    client = GitHubClient(
        token="explicit-token",
        settings=Settings(github_token="settings-token"),
        enable_cache=False,
    )

    try:
        assert client.token == "explicit-token"
        assert client.client.headers["Authorization"] == "Bearer explicit-token"
    finally:
        await client.client.aclose()
