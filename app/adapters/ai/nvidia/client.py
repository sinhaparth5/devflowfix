# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

import asyncio
from typing import Optional, Dict, Any, List
import httpx
import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    retry_if_exception_type,
)

from app.core.config import settings
from app.exceptions import NVIDIAAPIError

logger = structlog.get_logger(__name__)

OPENAI_COMPATIBLE_BASE_URL = "https://integrate.api.nvidia.com/v1"
LEGACY_PEXEC_BASE_URL = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions"


def _is_retryable_nvidia_error(exc: BaseException) -> bool:
    return isinstance(exc, NVIDIAAPIError) and exc.status_code in {429, 500, 502, 503, 504}

class NVIDIAClient:
    """
    HTTP client for NVIDIA NGC API.
    Provides authenticated requests with automatic retries and error handling
    """
    def __init__(
            self,
            api_key: Optional[str] = None,
            base_url: Optional[str] = None,
            timeout: Optional[int] = None,
            max_retries: Optional[int] = None,
    ):
        """
        Initialize NVIDIA API client.
        
        Args:
            api_key: NVIDIA NGC API key (defaults to settings)
            base_url: API base URL (defaults to settings)
            timeout: Request timeout in seconds (defaults to settings)
            max_retries: Maximum retry attempts (defaults to settings)
        """
        self.api_key = api_key or settings.nvidia_api_key
        self.base_url = self._normalize_base_url(base_url or settings.nvidia_api_base_url)
        self.timeout = timeout or settings.nvidia_api_timeout
        self.max_retries = max_retries or settings.nvidia_max_retries

        if not self.api_key:
            raise ValueError("NVIDIA API key is required")
        
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

        logger.info(
            "nvidia_client_initialized",
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

    _request_semaphore: Optional[asyncio.Semaphore] = None
    _request_semaphore_limit: Optional[int] = None

    @property
    def client(self) -> httpx.AsyncClient:
        return self._get_client()

    @client.setter
    def client(self, value: httpx.AsyncClient) -> None:
        self._client = value
        self._client_loop = self._current_loop()

    def _current_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def _create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            headers=self._get_headers(),
        )

    def _get_request_semaphore(self) -> asyncio.Semaphore:
        limit = settings.nvidia_max_concurrency
        if (
            self.__class__._request_semaphore is None
            or self.__class__._request_semaphore_limit != limit
        ):
            self.__class__._request_semaphore = asyncio.Semaphore(limit)
            self.__class__._request_semaphore_limit = limit
        return self.__class__._request_semaphore

    def _get_client(self) -> httpx.AsyncClient:
        loop = self._current_loop()
        loop_changed = (
            loop is not None
            and self._client_loop is not None
            and self._client_loop is not loop
        )

        if self._client is None or self._client.is_closed or loop_changed:
            if loop_changed:
                logger.warning("nvidia_client_recreated_for_event_loop")
            self._client = self._create_client()
            self._client_loop = loop
        elif self._client_loop is None and loop is not None:
            self._client_loop = loop

        return self._client

    def _normalize_base_url(self, base_url: Optional[str]) -> str:
        """
        Normalize NVIDIA API base URLs to the OpenAI-compatible endpoint used by this app.
        """
        normalized = (base_url or OPENAI_COMPATIBLE_BASE_URL).rstrip("/")

        if normalized == LEGACY_PEXEC_BASE_URL:
            logger.warning(
                "nvidia_legacy_base_url_detected",
                configured_base_url=normalized,
                normalized_base_url=OPENAI_COMPATIBLE_BASE_URL,
            )
            return OPENAI_COMPATIBLE_BASE_URL

        if normalized == "https://integrate.api.nvidia.com":
            return OPENAI_COMPATIBLE_BASE_URL

        return normalized

    def _get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for API requests.

        Returns:
            Dictionary of headers
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=(
            retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError))
            | retry_if_exception(_is_retryable_nvidia_error)
        ),
        reraise=True,
    )
    async def post(
        self,
        endpoint: str,
        data: Dict[str, Any],
        function_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Make POST request to NVIDIA API.
        
        Includes automatic retries for network errors.
        
        Args:
            endpoint: API endpoint (e.g., "/completions")
            data: Request payload
            function_id: Optional NGC function ID for endpoint
            
        Returns:
            Response JSON as dictionary
            
        Raises:
            NVIDIAAPIError: If API request fails
        """
        url = self._build_url(endpoint=endpoint, function_id=function_id)

        logger.debug(
            "nvidia_api_request",
            url=url,
            payload_size=len(str(data)),
        )
        try:
            async with self._get_request_semaphore():
                response = await self._get_client().post(url, json=data)

            logger.debug(
                "nvidia_api_response",
                url=url,
                status_code=response.status_code,
                response_size=len(response.text),
            )

            if response.status_code >= 400:
                error_detail = self._extract_error_detail(response)
                logger.error(
                    "nvidia_api_error",
                    url=url,
                    status_code=response.status_code,
                    error=error_detail,
                )
                raise NVIDIAAPIError(
                    error_detail or f"API request failed with status {response.status_code}",
                    status_code=response.status_code,
                )
            
            return response.json()
        except NVIDIAAPIError:
            raise
        except httpx.TimeoutException as e:
            logger.error("nvidia_api_timeout", url=url, timeout=self.timeout)
            raise NVIDIAAPIError(f"Request timed out after {self.timeout}s", status_code=504)
        except httpx.NetworkError as e:
            logger.error("nvidia_api_network_error", url=url, error=str(e))
            raise NVIDIAAPIError(f"Network error: {e}", status_code=503)
        except httpx.HTTPError as e:
            logger.error("nvidia_api_http_error", url=url, error=str(e))
            raise NVIDIAAPIError(f"Unexpected error: {e}")
    
        except Exception as e:
            logger.error("nvidia_api_unexpected_error", url=url, error=str(e), exc_info=True)
            raise NVIDIAAPIError(f"Unexpected error: {e}")
    
    async def get(self, endpoint: str) -> Dict[str, Any]:
        """
        Make GET request to NVIDIA API.

        Args:
            endpoint: API endpoint
        
        Returns:
            NVIDIAAPIError: If API request fails
        """
        url = self._build_url(endpoint=endpoint)

        try:
            response = await self._get_client().get(url)

            if response.status_code >= 400:
                error_detail = self._extract_error_detail(response)
                raise NVIDIAAPIError(
                    error_detail or f"API request failed with status {response.status_code}",
                    status_code=response.status_code,
                )
            return response.json()
        except httpx.HTTPError as e:
            logger.error("nvidia_api_error", url=url, error=str(e))
            raise NVIDIAAPIError(f"HTTP error: {e}")

    def _build_url(self, endpoint: str, function_id: Optional[str] = None) -> str:
        """
        Build an absolute NVIDIA API URL for either the OpenAI-compatible API or legacy function execution.
        """
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint

        clean_endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"

        if function_id:
            return f"{LEGACY_PEXEC_BASE_URL}/{function_id}{clean_endpoint}"

        return f"{self.base_url}{clean_endpoint}"
        
    def _extract_error_detail(self, response: httpx.Response) -> str:
        """
        Extract error detail from API response

        Args:
            response: HTTP response object
        
        Returns:
            Error detail string
        """
        try:
            error_json = response.json()

            if "error" in error_json:
                if isinstance(error_json["error"], dict):
                    return error_json["error"].get("message", str(error_json["error"]))
                return str(error_json["error"])
            
            if "detail" in error_json:
                return str(error_json["detail"])
            
            if "message" in error_json:
                return str(error_json["message"])
            
            return str(error_json)
        
        except Exception:
            return response.text
        
    async def close(self):
        """ Close the HTTP client """
        if self._client and not self._client.is_closed:
            try:
                await self._client.aclose()
            except RuntimeError as e:
                if "Event loop is closed" not in str(e):
                    raise
                logger.warning("nvidia_client_close_skipped_closed_loop")
        self._client = None
        self._client_loop = None
        logger.debug("nvidia_client_closed")

    async def __aenter__(self):
        """ Async context manager entry """
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """ Async context manager exit. """
        await self.close()

class NVIDIALLMClient(NVIDIAClient):
    """
    Specialized client for NVIDIA LLM API

    Handles completions and chat requests.
    """
    def __init__(self, model: Optional[str] = None, **kwargs):
        """
        Initialize LLM client.

        Args:   
            model: Model identifier (default to settings)
            **kwargs: Additional arguments for NVIDIAClient
        """
        super().__init__(**kwargs)
        self.model = model or settings.nvidia_llm_model

        logger.info("nvidia_llm_client_initialized", model=self.model)

    async def complete(
            self,
            prompt: str,
            max_tokens: int = 1000,
            temperature: float = 0.1,
            system_prompt: Optional[str] = None,
            **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate completion for prompt.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 = deterministic)
            **kwargs: Additional parameters

        Returns:
            API response with completion
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }

        logger.debug(
            "nvidia_llm_complete",
            model=self.model,
            prompt_length=len(prompt),
            max_tokens=max_tokens,
            temperature=temperature
        )

        # NVIDIA API uses standard OpenAI-compatible endpoint
        response = await self.post("/chat/completions", payload)

        usage = response.get("usage", {})
        logger.info(
            "nvidia_llm_complete_success",
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )

        return response
    
    def extract_text(self, response: Dict[str, Any]) -> str:
        """
        Extract text from completion response

        Args:
            response: API response

        Returns:
            Generated text
        """
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            logger.error("nvidia_llm_extract_text_failed", error=str(e), response=response)
            raise NVIDIAAPIError(f"Failed to extract text from the response: {e}")
        
class NVIDIAEmbeddingClient(NVIDIAClient):
    """
    Specialized client for NVIDIA embedding API.
    
    Handles text embedding generation.
    """
    
    def __init__(self, model: Optional[str] = None, **kwargs):
        """
        Initialize embedding client.
        
        Args:
            model: Model identifier (defaults to settings)
            **kwargs: Additional arguments for NVIDIAClient
        """
        super().__init__(**kwargs)
        self.model = model or settings.nvidia_embedding_model
        
        logger.info("nvidia_embedding_client_initialized", model=self.model)
    
    async def embed(
        self,
        texts: List[str],
        input_type: str = "query",
        **kwargs,
    ) -> List[List[float]]:
        """
        Generate embeddings for texts.
        
        Args:
            texts: List of texts to embed
            input_type: "query" or "passage"
            **kwargs: Additional parameters
            
        Returns:
            List of embedding vectors
        """
        payload = {
            "model": self.model,
            "input": texts if isinstance(texts, list) else [texts],
            "input_type": input_type,
            **kwargs,
        }
        
        logger.debug(
            "nvidia_embedding_embed",
            model=self.model,
            num_texts=len(payload["input"]),
            input_type=input_type,
        )
        
        response = await self.post("/embeddings", payload)
        
        # Extract embeddings
        try:
            embeddings = [item["embedding"] for item in response["data"]]            
            logger.info(
                "nvidia_embedding_embed_success",
                model=self.model,
                num_embeddings=len(embeddings),
                embedding_dim=len(embeddings[0]) if embeddings else 0,
            )
            
            return embeddings
            
        except (KeyError, IndexError) as e:
            logger.error("nvidia_embedding_extract_failed", error=str(e), response=response)
            raise NVIDIAAPIError(f"Failed to extract embeddings from response: {e}")
    
    async def embed_single(self, text: str, **kwargs) -> List[float]:
        """
        Generate embedding for single text.
        
        Args:
            text: Text to embed
            **kwargs: Additional parameters
            
        Returns:
            Embedding vector
        """
        embeddings = await self.embed([text], **kwargs)
        return embeddings[0]
