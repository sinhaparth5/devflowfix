# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

import json

import httpx
import pytest

from app.adapters.ai.nvidia.client import (
    LEGACY_PEXEC_BASE_URL,
    OPENAI_COMPATIBLE_BASE_URL,
    NVIDIAEmbeddingClient,
    NVIDIALLMClient,
)


@pytest.mark.asyncio
async def test_llm_client_normalizes_legacy_base_url() -> None:
    client = NVIDIALLMClient(
        api_key="test-key",
        base_url=LEGACY_PEXEC_BASE_URL,
    )

    assert client.base_url == OPENAI_COMPATIBLE_BASE_URL
    await client.close()


@pytest.mark.asyncio
async def test_llm_complete_calls_openai_compatible_chat_endpoint() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"category":"test"}'}}],
                "usage": {"total_tokens": 12},
            },
        )

    client = NVIDIALLMClient(api_key="test-key")
    await client.client.aclose()
    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=client._get_headers(),
    )

    response = await client.complete(prompt="analyze this", max_tokens=123, temperature=0.2)

    assert captured["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert '"model":' in str(captured["payload"])
    assert response["choices"][0]["message"]["content"] == '{"category":"test"}'
    await client.close()


@pytest.mark.asyncio
async def test_embedding_client_calls_embeddings_endpoint() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    client = NVIDIAEmbeddingClient(api_key="test-key")
    await client.client.aclose()
    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=client._get_headers(),
    )

    embedding = await client.embed_single("failure details", input_type="passage")

    assert captured["url"] == "https://integrate.api.nvidia.com/v1/embeddings"
    assert json.loads(str(captured["payload"]))["input_type"] == "passage"
    assert embedding == [0.1, 0.2, 0.3]
    await client.close()
