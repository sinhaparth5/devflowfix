# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

import json
import re
import hashlib
from typing import Dict, Any, Optional, List
import structlog

from app.adapters.ai.nvidia.client import NVIDIALLMClient
from app.adapters.ai.nvidia.prompts import (
    SYSTEM_PROMPT,
    build_classification_prompt,
    build_root_cause_analysis_prompt,
    build_remediation_validation_prompt,
    build_solution_generation_prompt,
)
from app.adapters.cache.redis import get_redis_cache, RedisCache
from app.core.enums import FailureType, Fixability, RemediationActionType
from app.exceptions import NVIDIAAPIError

logger = structlog.get_logger(__name__)

class LLMAdapter:
    """
    Adapter for LLM-based incident classification.
    
    Provides high-level interface for analyzing incidents using NVIDIA LLM.
    """
    
    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        enable_cache: bool = True,
    ):
        """
        Initialize LLM adapter.

        Args:
            model: Model identifier (defaults to settings)
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens in response
            enable_cache: Enable Redis caching for LLM responses
        """
        self.client = NVIDIALLMClient(model=model)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_cache = enable_cache
        self.cache: Optional[RedisCache] = None

        if enable_cache:
            self.cache = get_redis_cache()

        logger.info(
            "llm_adapter_initialized",
            model=self.client.model,
            temperature=temperature,
            max_tokens=max_tokens,
            cache_enabled=enable_cache,
        )

    def _generate_cache_key(self, prefix: str, *args) -> str:
        """
        Generate deterministic cache key from arguments.

        Args:
            prefix: Cache key prefix (e.g., 'classify', 'root_cause')
            *args: Arguments to hash for uniqueness

        Returns:
            Cache key string
        """
        # Combine all args into a single string
        combined = json.dumps(args, sort_keys=True, default=str)

        # Create SHA256 hash for uniqueness
        hash_obj = hashlib.sha256(combined.encode())
        hash_hex = hash_obj.hexdigest()[:16]  # Use first 16 chars

        # Return prefixed key
        return f"llm:{prefix}:{self.client.model}:{hash_hex}"
    
    async def classify(
        self,
        source: str,
        error_log: str,
        context: Dict[str, Any],
        similar_incidents: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Classify incident using LLM with Redis caching.

        Args:
            source: Incident source (github, argocd, kubernetes)
            error_log: Error log or message
            context: Additional context information
            similar_incidents: Optional similar incidents for context

        Returns:
            Classification result dictionary with:
                - failure_type: FailureType enum value
                - root_cause: str
                - fixability: Fixability enum value
                - confidence: float
                - recommended_action: RemediationActionType enum value
                - reasoning: str
                - key_indicators: List[str]
                - suggested_parameters: Dict[str, Any]

        Raises:
            NVIDIAAPIError: If API call fails
            ValueError: If response cannot be parsed
        """
        # Generate cache key from inputs
        cache_key = self._generate_cache_key(
            "classify",
            source,
            error_log[:500],  # Use first 500 chars for caching
            json.dumps(context, sort_keys=True, default=str),
        )

        # Try to get from cache
        if self.enable_cache and self.cache:
            try:
                await self.cache.connect()
                cached = await self.cache.get(cache_key)
                if cached:
                    logger.info(
                        "llm_classify_cache_hit",
                        source=source,
                        cache_key=cache_key,
                    )
                    # Reconstruct enums from cached strings
                    return self._normalize_classification(cached)
            except Exception as e:
                logger.warning("llm_classify_cache_failed", error=str(e))

        # Build prompt
        prompt = build_classification_prompt(
            source=source,
            error_log=error_log,
            context=context,
            similar_incidents=similar_incidents,
        )

        logger.info(
            "llm_classify_start",
            source=source,
            error_log_length=len(error_log),
            has_similar_incidents=bool(similar_incidents),
            num_similar=len(similar_incidents) if similar_incidents else 0,
        )

        try:
            # Call LLM
            response = await self.client.complete(
                prompt=prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            # Extract text
            text = self.client.extract_text(response)

            # Parse JSON response
            classification = self._parse_classification_response(text)

            # Validate and normalize
            classification = self._normalize_classification(classification)

            # Cache the result (serialize enums to strings for caching)
            if self.enable_cache and self.cache:
                try:
                    cacheable = {
                        "failure_type": classification["failure_type"].value if hasattr(classification["failure_type"], "value") else str(classification["failure_type"]),
                        "root_cause": classification["root_cause"],
                        "fixability": classification["fixability"].value if hasattr(classification["fixability"], "value") else str(classification["fixability"]),
                        "confidence": classification["confidence"],
                        "recommended_action": classification["recommended_action"].value if hasattr(classification["recommended_action"], "value") else str(classification["recommended_action"]),
                        "reasoning": classification["reasoning"],
                        "key_indicators": classification["key_indicators"],
                        "suggested_parameters": classification["suggested_parameters"],
                    }
                    await self.cache.set(cache_key, cacheable, ttl=86400)  # 24 hours
                    logger.debug("llm_classify_cached", cache_key=cache_key)
                except Exception as e:
                    logger.warning("llm_classify_cache_set_failed", error=str(e))

            logger.info(
                "llm_classify_success",
                failure_type=classification.get("failure_type"),
                fixability=classification.get("fixability"),
                confidence=classification.get("confidence"),
                action=classification.get("recommended_action"),
            )

            return classification

        except Exception as e:
            logger.error(
                "llm_classify_failed",
                error=str(e),
                source=source,
                exc_info=True,
            )
            raise
    
    def _parse_classification_response(self, text: str) -> Dict[str, Any]:
        """
        Parse LLM response into classification dict.
        
        Handles various response formats and extracts JSON.
        
        Args:
            text: LLM response text
            
        Returns:
            Parsed classification dictionary
            
        Raises:
            ValueError: If JSON cannot be extracted or parsed
        """
        # Try to extract JSON from response
        # LLM might wrap JSON in markdown code blocks
        json_text = text.strip()
        
        # Remove markdown code blocks if present
        if "```json" in json_text:
            json_text = re.search(r"```json\s*(\{.*?\})\s*```", json_text, re.DOTALL)
            if json_text:
                json_text = json_text.group(1)
        elif "```" in json_text:
            json_text = re.search(r"```\s*(\{.*?\})\s*```", json_text, re.DOTALL)
            if json_text:
                json_text = json_text.group(1)
        
        # Find JSON object
        if not json_text.startswith("{"):
            # Try to find JSON object in text
            json_match = re.search(r"\{.*\}", json_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
            else:
                raise ValueError("No JSON object found in LLM response")
        
        try:
            classification = json.loads(json_text)
            logger.debug("llm_response_parsed", classification_keys=list(classification.keys()))
            return classification
            
        except json.JSONDecodeError as e:
            logger.error(
                "llm_response_parse_failed",
                error=str(e),
                response_text=json_text[:500],
            )
            raise ValueError(f"Failed to parse JSON response: {e}")
    
    def _parse_solution_response(self, text: str) -> Dict[str, Any]:
        """
        Parse LLM solution response into solution dictionary.
        
        Args:
            text: LLM response text containing solution JSON
            
        Returns:
            Parsed solution dictionary
            
        Raises:
            ValueError: If JSON cannot be extracted or parsed
        """
        json_text = text.strip()
        
        # Remove markdown code blocks if present
        if "```json" in json_text:
            json_match = re.search(r"```json\s*(\{.*?\})\s*```", json_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(1)
        elif "```" in json_text:
            json_match = re.search(r"```\s*(\{.*?\})\s*```", json_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(1)
        
        # Find JSON object
        if not json_text.startswith("{"):
            json_match = re.search(r"\{.*\}", json_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
        
        # Try to find the last closing brace to handle truncated JSON
        if json_text.count('{') > json_text.count('}'):
            last_brace = json_text.rfind('}')
            if last_brace > 0:
                json_text = json_text[:last_brace + 1]
        
        try:
            solution = json.loads(json_text)
            logger.debug("solution_response_parsed", solution_keys=list(solution.keys()))
            return solution
        except json.JSONDecodeError as e:
            logger.error(
                "solution_response_parse_failed",
                error=str(e),
                response_length=len(json_text),
            )
            # Return a minimal solution structure instead of failing
            return {
                "immediate_fix": {
                    "description": text[:500],
                    "steps": ["Review error logs", "Check configuration", "Apply fix"]
                },
                "code_changes": [],
                "configuration_changes": [],
                "prevention_measures": []
            }
    
    def _normalize_classification(self, classification: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize and validate classification result.
        
        Converts string values to enums and ensures required fields.
        
        Args:
            classification: Raw classification dictionary
            
        Returns:
            Normalized classification dictionary
        """
        normalized = {}
        
        # Normalize failure_type
        failure_type_str = classification.get("failure_type", "unknown").lower()
        try:
            normalized["failure_type"] = FailureType(failure_type_str)
        except ValueError:
            logger.warning(
                "invalid_failure_type",
                value=failure_type_str,
                using_default="unknown",
            )
            normalized["failure_type"] = FailureType.UNKNOWN
        
        # Normalize fixability
        fixability_str = classification.get("fixability", "unknown").lower()
        try:
            normalized["fixability"] = Fixability(fixability_str)
        except ValueError:
            logger.warning(
                "invalid_fixability",
                value=fixability_str,
                using_default="unknown",
            )
            normalized["fixability"] = Fixability.UNKNOWN
        
        # Normalize recommended_action
        action_str = classification.get("recommended_action", "notify_only").lower()
        try:
            normalized["recommended_action"] = RemediationActionType(action_str)
        except ValueError:
            logger.warning(
                "invalid_action_type",
                value=action_str,
                using_default="notify_only",
            )
            normalized["recommended_action"] = RemediationActionType.NOTIFY_ONLY
        
        # Copy other fields
        normalized["root_cause"] = classification.get("root_cause", "Unknown error")
        normalized["confidence"] = float(classification.get("confidence", 0.5))
        normalized["reasoning"] = classification.get("reasoning", "")
        normalized["key_indicators"] = classification.get("key_indicators", [])
        normalized["suggested_parameters"] = classification.get("suggested_parameters", {})
        
        # Clamp confidence to [0.0, 1.0]
        normalized["confidence"] = max(0.0, min(1.0, normalized["confidence"]))
        
        return normalized
    
    async def analyze_root_cause(
        self,
        error_log: str,
        context: Dict[str, Any],
        stack_trace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform detailed root cause analysis with Redis caching.

        Args:
            error_log: Error log or message
            context: Additional context
            stack_trace: Optional stack trace

        Returns:
            Root cause analysis dictionary
        """
        # Generate cache key
        cache_key = self._generate_cache_key(
            "root_cause",
            error_log[:1000],
            json.dumps(context, sort_keys=True, default=str),
            stack_trace[:500] if stack_trace else "",
        )

        # Try to get from cache
        if self.enable_cache and self.cache:
            try:
                await self.cache.connect()
                cached = await self.cache.get(cache_key)
                if cached:
                    logger.info("llm_root_cause_cache_hit", cache_key=cache_key)
                    return cached
            except Exception as e:
                logger.warning("llm_root_cause_cache_failed", error=str(e))

        prompt = build_root_cause_analysis_prompt(
            error_log=error_log,
            context=context,
            stack_trace=stack_trace,
        )

        logger.info("llm_root_cause_analysis_start")

        try:
            response = await self.client.complete(
                prompt=prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            text = self.client.extract_text(response)
            analysis = self._parse_classification_response(text)

            # Cache the result
            if self.enable_cache and self.cache:
                try:
                    await self.cache.set(cache_key, analysis, ttl=172800)  # 48 hours
                    logger.debug("llm_root_cause_cached", cache_key=cache_key)
                except Exception as e:
                    logger.warning("llm_root_cause_cache_set_failed", error=str(e))

            logger.info("llm_root_cause_analysis_success")
            return analysis

        except Exception as e:
            logger.error("llm_root_cause_analysis_failed", error=str(e))
            raise
    
    async def validate_remediation(
        self,
        failure_type: str,
        proposed_action: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validate proposed remediation action with Redis caching.

        Args:
            failure_type: Classified failure type
            proposed_action: Proposed remediation action
            context: Incident context

        Returns:
            Validation result dictionary
        """
        # Generate cache key
        cache_key = self._generate_cache_key(
            "validate",
            failure_type,
            proposed_action,
            json.dumps(context, sort_keys=True, default=str),
        )

        # Try to get from cache
        if self.enable_cache and self.cache:
            try:
                await self.cache.connect()
                cached = await self.cache.get(cache_key)
                if cached:
                    logger.info("llm_validate_cache_hit", cache_key=cache_key)
                    return cached
            except Exception as e:
                logger.warning("llm_validate_cache_failed", error=str(e))

        prompt = build_remediation_validation_prompt(
            failure_type=failure_type,
            proposed_action=proposed_action,
            context=context,
        )

        logger.info("llm_validate_remediation_start", action=proposed_action)

        try:
            response = await self.client.complete(
                prompt=prompt,
                max_tokens=1000,
                temperature=self.temperature,
            )

            text = self.client.extract_text(response)
            validation = self._parse_classification_response(text)

            # Cache the result
            if self.enable_cache and self.cache:
                try:
                    await self.cache.set(cache_key, validation, ttl=259200)  # 72 hours
                    logger.debug("llm_validate_cached", cache_key=cache_key)
                except Exception as e:
                    logger.warning("llm_validate_cache_set_failed", error=str(e))

            logger.info(
                "llm_validate_remediation_success",
                is_safe=validation.get("is_safe"),
                risk_level=validation.get("risk_level"),
            )

            return validation

        except Exception as e:
            logger.error("llm_validate_remediation_failed", error=str(e))
            raise
    
    async def generate_solution(
        self,
        error_log: str,
        failure_type: str,
        root_cause: str,
        context: Dict[str, Any],
        repository_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate detailed solutions for fixing the error with Redis caching.

        Args:
            error_log: Error log or message
            failure_type: Classified failure type
            root_cause: Root cause analysis
            context: Incident context
            repository_code: Optional relevant code from repository

        Returns:
            Solution dictionary with immediate_fix, code_changes, config_changes, etc.
        """
        # Generate cache key
        cache_key = self._generate_cache_key(
            "solution",
            failure_type,
            root_cause[:500],
            error_log[:300],
            repository_code[:500] if repository_code else "",
        )

        # Try to get from cache
        if self.enable_cache and self.cache:
            try:
                await self.cache.connect()
                cached = await self.cache.get(cache_key)
                if cached:
                    logger.info(
                        "llm_solution_cache_hit",
                        cache_key=cache_key,
                        failure_type=failure_type,
                    )
                    return cached
            except Exception as e:
                logger.warning("llm_solution_cache_failed", error=str(e))

        prompt = build_solution_generation_prompt(
            error_log=error_log,
            failure_type=failure_type,
            root_cause=root_cause,
            context=context,
            repository_code=repository_code,
        )

        logger.info(
            "llm_generate_solution_start",
            failure_type=failure_type,
            has_code=bool(repository_code),
        )

        try:
            response = await self.client.complete(
                prompt=prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            text = self.client.extract_text(response)
            solution = self._parse_solution_response(text)

            # Cache the result
            if self.enable_cache and self.cache:
                try:
                    await self.cache.set(cache_key, solution, ttl=604800)  # 7 days
                    logger.debug("llm_solution_cached", cache_key=cache_key)
                except Exception as e:
                    logger.warning("llm_solution_cache_set_failed", error=str(e))

            logger.info(
                "llm_generate_solution_success",
                failure_type=failure_type,
                has_immediate_fix=bool(solution.get("immediate_fix")),
                has_code_changes=bool(solution.get("code_changes")),
                num_config_changes=len(solution.get("configuration_changes") or []),
            )
            return solution

        except Exception as e:
            logger.error(
                "llm_generate_solution_failed",
                failure_type=failure_type,
                error=str(e),
                exc_info=True,
            )
            raise
    
    async def close(self):
        """Close the LLM client."""
        await self.client.close()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()