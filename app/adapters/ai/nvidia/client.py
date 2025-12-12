# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, Dict, Any, List
import httpx
import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.core.config import settings
from app.exceptions import NVIDIAAPIError

logger = structlog.get_logger(__name__)

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
        self.base_url = base_url or settings.nvidia_api_base_url
        self.timeout = timeout or settings.nvidia_api_timeout
        self.max_retries = max_retries or settings.nvidia_max_retries

        if not self.api_key:
            raise ValueError("NVIDIA API key is required")
        
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            headers=self._get_headers(),
        )

        logger.info(
            "nvidia_client_initialized",
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

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
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
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
        if function_id:
            url = f"{self.base_url}/{function_id}{endpoint}"
        else:
            url = endpoint if endpoint.startswith("http") else f"{self.base_url}{endpoint}"

        logger.debug(
            "nvidia_api_request",
            url=url,
            payload_size=len(str(data)),
        )
        try:
            response = await self.client.post(url, json=data)

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
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}{endpoint}"

        try:
            response = await self.client.get(url)

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
        await self.client.aclose()
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
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
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