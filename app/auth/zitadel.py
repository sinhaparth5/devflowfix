# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Zitadel Authentication

JWT validation and user extraction for Zitadel OIDC tokens.
"""

from datetime import datetime, timezone
from typing import Optional, Annotated
from dataclasses import dataclass, field
import httpx
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.auth.config import get_zitadel_settings, ZitadelSettings
from app.dependencies import get_db
from app.adapters.database.postgres.models import UserTable

logger = structlog.get_logger(__name__)

# Security scheme for OpenAPI docs
security = HTTPBearer(auto_error=False)


@dataclass
class ZitadelUser:
    """
    Represents an authenticated Zitadel user.

    This is the user object available in your route handlers.
    """

    # Zitadel user ID (unique identifier)
    sub: str

    # User's email
    email: str

    # Whether email is verified
    email_verified: bool = False

    # Display name
    name: str = ""

    # Given name (first name)
    given_name: str = ""

    # Family name (last name)
    family_name: str = ""

    # Preferred username
    preferred_username: str = ""

    # Profile picture URL
    picture: str = ""

    # Locale
    locale: str = ""

    # Raw token claims (for advanced use)
    claims: dict = field(default_factory=dict)

    # Database user record (populated after DB lookup)
    db_user: Optional[UserTable] = None

    @property
    def user_id(self) -> str:
        """Alias for sub (Zitadel user ID)."""
        return self.sub

    @property
    def display_name(self) -> str:
        """Get best available display name."""
        return self.name or self.preferred_username or self.email.split("@")[0]

    @classmethod
    def from_claims(cls, claims: dict) -> "ZitadelUser":
        """
        Create ZitadelUser from JWT claims.

        Args:
            claims: JWT token claims dictionary

        Returns:
            ZitadelUser instance
        """
        return cls(
            sub=claims.get("sub", ""),
            email=claims.get("email", ""),
            email_verified=claims.get("email_verified", False),
            name=claims.get("name", ""),
            given_name=claims.get("given_name", ""),
            family_name=claims.get("family_name", ""),
            preferred_username=claims.get("preferred_username", ""),
            picture=claims.get("picture", ""),
            locale=claims.get("locale", ""),
            claims=claims,
        )


class ZitadelAuth:
    """
    Zitadel authentication handler for PKCE/Public Client applications.

    Validates opaque tokens using Zitadel's Userinfo endpoint.
    This works with public clients (User Agent apps) that use PKCE.
    """

    def __init__(self, settings: ZitadelSettings):
        self.settings = settings
        # Cache for userinfo results (short TTL for security)
        self._userinfo_cache: dict[str, tuple[dict, datetime]] = {}
        self._cache_ttl_seconds = 30  # Short cache for security

    def _get_cached_userinfo(self, token: str) -> Optional[dict]:
        """Get cached userinfo result if still valid."""
        if token in self._userinfo_cache:
            claims, cached_at = self._userinfo_cache[token]
            age = (datetime.now(timezone.utc) - cached_at).total_seconds()
            if age < self._cache_ttl_seconds:
                return claims
            # Remove expired cache entry
            del self._userinfo_cache[token]
        return None

    def _cache_userinfo(self, token: str, claims: dict) -> None:
        """Cache userinfo result."""
        # Limit cache size to prevent memory issues
        if len(self._userinfo_cache) > 1000:
            # Clear oldest entries
            self._userinfo_cache.clear()
        self._userinfo_cache[token] = (claims, datetime.now(timezone.utc))

    async def get_userinfo(self, token: str) -> dict:
        """
        Validate token using Zitadel's userinfo endpoint.

        This validates opaque tokens by calling Zitadel's userinfo API.
        Works with PKCE/public client applications (no client secret needed).

        Args:
            token: Access token string (opaque)

        Returns:
            User info dictionary with claims

        Raises:
            HTTPException: If token is invalid or expired
        """
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No token provided",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check cache first
        cached = self._get_cached_userinfo(token)
        if cached:
            logger.debug("userinfo_cache_hit", sub=cached.get("sub"))
            return cached

        # Call userinfo endpoint
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.settings.userinfo_uri,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                    timeout=10.0,
                )

                if response.status_code == 401:
                    logger.warning(
                        "userinfo_unauthorized",
                        token_preview=token[:20] + "...",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid or expired token",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

                if response.status_code != 200:
                    logger.warning(
                        "userinfo_request_failed",
                        status_code=response.status_code,
                        response=response.text[:200],
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token validation failed",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

                result = response.json()

                # Userinfo must have a sub claim
                if not result.get("sub"):
                    logger.warning("userinfo_missing_sub", result=result)
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token: missing user identifier",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

                logger.debug(
                    "userinfo_fetched",
                    sub=result.get("sub"),
                    email=result.get("email"),
                )

                # Cache the result
                self._cache_userinfo(token, result)

                return result

        except HTTPException:
            raise
        except httpx.TimeoutException:
            logger.error("userinfo_timeout")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service timeout",
            )
        except httpx.HTTPError as e:
            logger.error("userinfo_error", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            )

    async def validate_token(self, token: str) -> dict:
        """
        Validate a token and return claims.

        Uses userinfo endpoint to validate opaque tokens from PKCE flow.

        Args:
            token: Access token string

        Returns:
            Token claims dictionary

        Raises:
            HTTPException: If token is invalid
        """
        return await self.get_userinfo(token)

    async def get_user_from_token(self, token: str) -> ZitadelUser:
        """
        Validate token and return ZitadelUser.

        Args:
            token: JWT access token

        Returns:
            ZitadelUser with claims
        """
        claims = await self.validate_token(token)
        return ZitadelUser.from_claims(claims)


# Global auth instance (lazy initialized)
_auth_instance: Optional[ZitadelAuth] = None


def get_auth() -> ZitadelAuth:
    """Get or create ZitadelAuth instance."""
    global _auth_instance
    if _auth_instance is None:
        settings = get_zitadel_settings()
        _auth_instance = ZitadelAuth(settings)
    return _auth_instance


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> ZitadelUser:
    """
    FastAPI dependency to get current authenticated user.

    Usage:
        @router.get("/protected")
        async def protected_route(user: ZitadelUser = Depends(get_current_user)):
            return {"user_id": user.sub, "email": user.email}

    Raises:
        HTTPException: 401 if not authenticated or token invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth = get_auth()
    return await auth.get_user_from_token(credentials.credentials)


async def get_current_active_user(
    user: ZitadelUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    FastAPI dependency to get current user with database record.

    This dependency:
    1. Validates the Zitadel token
    2. Finds or creates the user in the database
    3. Returns both the Zitadel user info and database record

    Usage:
        @router.get("/profile")
        async def get_profile(current_user: dict = Depends(get_current_active_user)):
            user = current_user["user"]  # ZitadelUser
            db_user = current_user["db_user"]  # UserTable
    """
    # Find or create user in database
    db_user = db.query(UserTable).filter(
        UserTable.user_id == user.sub
    ).first()

    if not db_user:
        # Auto-create user on first login
        db_user = UserTable(
            user_id=user.sub,
            email=user.email,
            full_name=user.name or f"{user.given_name} {user.family_name}".strip(),
            avatar_url=user.picture,
            is_active=True,
            is_verified=user.email_verified,
            oauth_provider="zitadel",
            oauth_id=user.sub,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        logger.info(
            "user_auto_created",
            user_id=user.sub,
            email=user.email,
        )
    else:
        # Sync user info from Zitadel on every login
        updated = False

        # Always sync these fields from Zitadel (source of truth)
        new_full_name = user.name or f"{user.given_name} {user.family_name}".strip()

        if db_user.email != user.email:
            db_user.email = user.email
            updated = True

        if new_full_name and db_user.full_name != new_full_name:
            db_user.full_name = new_full_name
            updated = True

        if user.picture and db_user.avatar_url != user.picture:
            db_user.avatar_url = user.picture
            updated = True

        if db_user.is_verified != user.email_verified:
            db_user.is_verified = user.email_verified
            updated = True

        # Always update last login
        db_user.last_login_at = datetime.now(timezone.utc)

        if updated:
            db_user.updated_at = datetime.now(timezone.utc)
            logger.info(
                "user_synced_from_zitadel",
                user_id=user.sub,
                email=user.email,
            )

        db.commit()

    # Check if user is active
    if not db_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    # Attach database user to ZitadelUser
    user.db_user = db_user

    return {
        "user": user,
        "db_user": db_user,
    }


async def get_optional_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> Optional[ZitadelUser]:
    """
    FastAPI dependency to optionally get current user.

    Returns None if not authenticated (instead of raising exception).

    Usage:
        @router.get("/public")
        async def public_route(user: Optional[ZitadelUser] = Depends(get_optional_user)):
            if user:
                return {"message": f"Hello, {user.name}"}
            return {"message": "Hello, guest"}
    """
    if not credentials:
        return None

    try:
        auth = get_auth()
        return await auth.get_user_from_token(credentials.credentials)
    except HTTPException:
        return None


async def require_admin(
    current_user_data: dict = Depends(get_current_active_user),
) -> dict:
    """
    FastAPI dependency to require admin role.

    Usage:
        @router.delete("/users/{user_id}")
        async def delete_user(admin: dict = Depends(require_admin)):
            # Only admins can reach here
            ...

    Raises:
        HTTPException: 403 if user is not an admin
    """
    db_user = current_user_data.get("db_user")

    if not db_user or db_user.role not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user_data
