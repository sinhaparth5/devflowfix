# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

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
            timeout: Optional[str] = None,
            max_retries: Optional[str] = None,
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