# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.

from app.adapters.ai.nvidia.llm import LLMAdapter


def test_parse_classification_response_falls_back_for_malformed_json() -> None:
    adapter = LLMAdapter(enable_cache=False)

    parsed = adapter._parse_classification_response(
        '{'
        '"failure_type":"testfailure",'
        '"root_cause":"Assertion error",'
        '"fixability":"manual",'
        '"confidence":0.95,'
        '"recommended_action":"noop",'
        '"reasoning":"Bad JSON output",'
        '"key_indicators":["AssertionError"]'
    )

    assert parsed["failure_type"] == "unknown"
    assert parsed["fixability"] == "unknown"
    assert parsed["recommended_action"] == "notify_only"
    assert parsed["confidence"] == 0.3
