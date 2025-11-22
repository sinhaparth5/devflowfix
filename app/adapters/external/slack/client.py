# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""
Slack API Client

Provides HTTP client for interacting with Slack API with:
- Bot token authentication
- Automatic retries with exponential backoff
- Circuit breaker for fault tolerance
- Rate limit handling
- Comprehensive error handling
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx

from app.core.config import Settings
from app.exceptions import SlackAPIError
from app.utils.logging import get_logger
from app.utils.retry import retry
from app.utils.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)


class SlackClient:
    """
    HTTP client for Slack API.
    
    Features:
    - Bot token authentication
    - Automatic retries with exponential backoff
    - Circuit breaker pattern for fault tolerance
    - Rate limit tracking and handling
    - Comprehensive error handling
    
    Example:
        ```python
        client = SlackClient(token="xoxb-...")
        
        # Post message
        await client.post_message(
            channel="#incidents",
            text="CI/CD pipeline failed!"
        )
        
        # Search messages
        results = await client.search_messages(
            query="error",
            count=10
        )
        ```
    """
    
    BASE_URL = "https://slack.com/api"
    
    def __init__(
        self,
        token: Optional[str] = None,
        settings: Optional[Settings] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize Slack client.
        
        Args:
            token: Slack bot token (xoxb-...)
            settings: Application settings
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.settings = settings or Settings()
        self.token = token or self.settings.slack_token
        self.timeout = timeout
        self.max_retries = max_retries
        
        if not self.token:
            logger.warning("slack_client_no_token", message="Slack token not configured")
        
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            headers=self._get_default_headers(),
        )
        
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            success_threshold=2,
            timeout=60.0,
            expected_exception=SlackAPIError,
            name="slack_api",
        )
        
        self._rate_limit_remaining: Optional[int] = None
        self._rate_limit_reset: Optional[datetime] = None
    
    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for Slack API requests."""
        headers = {
            "Content-Type": "application/json; charset=utf-8",
        }
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        return headers
    
    def _update_rate_limit(self, headers: httpx.Headers) -> None:
        """Update rate limit information from response headers."""
        if "retry-after" in headers:
            retry_after = int(headers["retry-after"])
            self._rate_limit_reset = datetime.now()
            self._rate_limit_reset = self._rate_limit_reset.replace(
                second=self._rate_limit_reset.second + retry_after
            )
            
            logger.debug(
                "slack_rate_limit_updated",
                retry_after=retry_after,
                reset_at=self._rate_limit_reset.isoformat() if self._rate_limit_reset else None,
            )
    
    def _check_rate_limit(self) -> None:
        """Check if we're about to hit rate limit."""
        if self._rate_limit_reset and datetime.now() < self._rate_limit_reset:
            wait_seconds = (self._rate_limit_reset - datetime.now()).total_seconds()
            
            logger.warning(
                "slack_rate_limit_active",
                wait_seconds=wait_seconds,
                reset_at=self._rate_limit_reset.isoformat(),
            )
            
            raise SlackAPIError(
                f"Slack API rate limit active. Retry after {wait_seconds:.0f} seconds.",
                status_code=429,
            )
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Slack API with error handling.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for httpx request
            
        Returns:
            Response JSON data
            
        Raises:
            SlackAPIError: On API errors
        """
        self._check_rate_limit()
        
        try:
            response = await self.client.request(method, endpoint, **kwargs)
            
            self._update_rate_limit(response.headers)
            
            if response.status_code >= 400:
                error_data = {}
                try:
                    error_data = response.json()
                except Exception:
                    pass
                
                error_message = error_data.get("error", response.text)
                
                logger.error(
                    "slack_api_http_error",
                    method=method,
                    endpoint=endpoint,
                    status_code=response.status_code,
                    message=error_message,
                )
                
                raise SlackAPIError(
                    f"Slack API HTTP error: {error_message}",
                    status_code=response.status_code,
                )
            
            data = response.json()
            
            if not data.get("ok", False):
                error = data.get("error", "unknown_error")
                error_detail = data.get("error_detail", "")
                
                logger.error(
                    "slack_api_error",
                    method=method,
                    endpoint=endpoint,
                    error=error,
                    error_detail=error_detail,
                )
                
                raise SlackAPIError(
                    f"Slack API error: {error}" + (f" - {error_detail}" if error_detail else ""),
                    status_code=response.status_code,
                )
            
            return data
        
        except httpx.HTTPError as e:
            logger.error(
                "slack_http_error",
                method=method,
                endpoint=endpoint,
                error=str(e),
            )
            raise SlackAPIError(f"HTTP error calling Slack API: {e}") from e
    
    @retry(
        max_attempts=3,
        base_delay=1.0,
        exponential_backoff=True,
        exceptions=(SlackAPIError,),
    )
    async def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make GET request to Slack API.
        
        Args:
            endpoint: API endpoint
            **kwargs: Additional request parameters
            
        Returns:
            Response JSON data
        """
        return await self.circuit_breaker._call_async(
            self._request,
            "GET",
            endpoint,
            **kwargs,
        )
    
    @retry(
        max_attempts=3,
        base_delay=1.0,
        exponential_backoff=True,
        exceptions=(SlackAPIError,),
    )
    async def post(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make POST request to Slack API.
        
        Args:
            endpoint: API endpoint
            json: JSON body data
            **kwargs: Additional request parameters
            
        Returns:
            Response JSON data
        """
        return await self.circuit_breaker._call_async(
            self._request,
            "POST",
            endpoint,
            json=json,
            **kwargs,
        )
    
    
    async def post_message(
        self,
        channel: str,
        text: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None,
        thread_ts: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Post a message to a channel.
        
        Args:
            channel: Channel ID or name (#channel)
            text: Message text (fallback if blocks used)
            blocks: Message blocks for rich formatting
            thread_ts: Thread timestamp to reply in thread
            **kwargs: Additional chat.postMessage parameters
            
        Returns:
            Message response data
        """
        endpoint = "/chat.postMessage"
        
        payload = {
            "channel": channel,
            **kwargs,
        }
        
        if text:
            payload["text"] = text
        
        if blocks:
            payload["blocks"] = blocks
        
        if thread_ts:
            payload["thread_ts"] = thread_ts
        
        logger.info(
            "slack_post_message",
            channel=channel,
            has_blocks=bool(blocks),
            in_thread=bool(thread_ts),
        )
        
        return await self.post(endpoint, json=payload)
    
    async def update_message(
        self,
        channel: str,
        ts: str,
        text: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Update an existing message.
        
        Args:
            channel: Channel ID or name
            ts: Timestamp of message to update
            text: New message text
            blocks: New message blocks
            **kwargs: Additional chat.update parameters
            
        Returns:
            Updated message response
        """
        endpoint = "/chat.update"
        
        payload = {
            "channel": channel,
            "ts": ts,
            **kwargs,
        }
        
        if text:
            payload["text"] = text
        
        if blocks:
            payload["blocks"] = blocks
        
        logger.info(
            "slack_update_message",
            channel=channel,
            ts=ts,
        )
        
        return await self.post(endpoint, json=payload)
    
    async def delete_message(
        self,
        channel: str,
        ts: str,
    ) -> Dict[str, Any]:
        """
        Delete a message.
        
        Args:
            channel: Channel ID or name
            ts: Timestamp of message to delete
            
        Returns:
            Delete response
        """
        endpoint = "/chat.delete"
        
        payload = {
            "channel": channel,
            "ts": ts,
        }
        
        logger.info(
            "slack_delete_message",
            channel=channel,
            ts=ts,
        )
        
        return await self.post(endpoint, json=payload)
    
    
    async def search_messages(
        self,
        query: str,
        count: int = 20,
        page: int = 1,
        sort: str = "timestamp",
        sort_dir: str = "desc",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Search for messages.
        
        Args:
            query: Search query
            count: Number of results per page
            page: Page number
            sort: Sort field (timestamp or score)
            sort_dir: Sort direction (asc or desc)
            **kwargs: Additional search.messages parameters
            
        Returns:
            Search results
        """
        endpoint = "/search.messages"
        
        params = {
            "query": query,
            "count": count,
            "page": page,
            "sort": sort,
            "sort_dir": sort_dir,
            **kwargs,
        }
        
        logger.info(
            "slack_search_messages",
            query=query,
            count=count,
            page=page,
        )
        
        return await self.get(endpoint, params=params)
    
    
    async def list_channels(
        self,
        exclude_archived: bool = True,
        limit: int = 100,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        List public channels.
        
        Args:
            exclude_archived: Exclude archived channels
            limit: Maximum channels to return
            **kwargs: Additional conversations.list parameters
            
        Returns:
            List of channels
        """
        endpoint = "/conversations.list"
        
        params = {
            "exclude_archived": exclude_archived,
            "limit": limit,
            "types": "public_channel",
            **kwargs,
        }
        
        response = await self.get(endpoint, params=params)
        return response.get("channels", [])
    
    async def get_channel_info(
        self,
        channel: str,
    ) -> Dict[str, Any]:
        """
        Get information about a channel.
        
        Args:
            channel: Channel ID
            
        Returns:
            Channel information
        """
        endpoint = "/conversations.info"
        
        params = {"channel": channel}
        
        response = await self.get(endpoint, params=params)
        return response.get("channel", {})
    
    async def get_channel_history(
        self,
        channel: str,
        limit: int = 100,
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Get channel message history.
        
        Args:
            channel: Channel ID
            limit: Maximum messages to return
            oldest: Oldest timestamp (exclusive)
            latest: Latest timestamp (inclusive)
            **kwargs: Additional conversations.history parameters
            
        Returns:
            List of messages
        """
        endpoint = "/conversations.history"
        
        params = {
            "channel": channel,
            "limit": limit,
            **kwargs,
        }
        
        if oldest:
            params["oldest"] = oldest
        
        if latest:
            params["latest"] = latest
        
        response = await self.get(endpoint, params=params)
        return response.get("messages", [])
    
    
    async def get_user_info(
        self,
        user: str,
    ) -> Dict[str, Any]:
        """
        Get information about a user.
        
        Args:
            user: User ID
            
        Returns:
            User information
        """
        endpoint = "/users.info"
        
        params = {"user": user}
        
        response = await self.get(endpoint, params=params)
        return response.get("user", {})
    
    
    async def add_reaction(
        self,
        channel: str,
        timestamp: str,
        name: str,
    ) -> Dict[str, Any]:
        """
        Add reaction to a message.
        
        Args:
            channel: Channel ID
            timestamp: Message timestamp
            name: Reaction emoji name (without colons)
            
        Returns:
            Reaction response
        """
        endpoint = "/reactions.add"
        
        payload = {
            "channel": channel,
            "timestamp": timestamp,
            "name": name,
        }
        
        logger.info(
            "slack_add_reaction",
            channel=channel,
            timestamp=timestamp,
            name=name,
        )
        
        return await self.post(endpoint, json=payload)
    
    
    async def upload_file(
        self,
        channels: str,
        content: Optional[str] = None,
        file: Optional[bytes] = None,
        filename: Optional[str] = None,
        title: Optional[str] = None,
        initial_comment: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Upload a file to Slack.
        
        Args:
            channels: Comma-separated channel IDs
            content: File content as text
            file: File content as bytes
            filename: Filename
            title: File title
            initial_comment: Comment to add with file
            **kwargs: Additional files.upload parameters
            
        Returns:
            File upload response
        """
        endpoint = "/files.upload"
        
        payload = {
            "channels": channels,
            **kwargs,
        }
        
        if content:
            payload["content"] = content
        
        if filename:
            payload["filename"] = filename
        
        if title:
            payload["title"] = title
        
        if initial_comment:
            payload["initial_comment"] = initial_comment
        
        logger.info(
            "slack_upload_file",
            channels=channels,
            filename=filename,
        )
        
        return await self.post(endpoint, json=payload)
    
    
    async def auth_test(self) -> Dict[str, Any]:
        """
        Test authentication and get bot info.
        
        Returns:
            Authentication information
        """
        endpoint = "/auth.test"
        return await self.post(endpoint)
    
    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """
        Get circuit breaker status.
        
        Returns:
            Circuit breaker statistics
        """
        return self.circuit_breaker.get_stats()
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
