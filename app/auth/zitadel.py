# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

"""
Zitadel Authentication

JWT validation and user extraction for Zitadel OIDC tokens.
"""

from datetime import datetime, timezone
from typing import Optional, Annotated, Any
from dataclasses import dataclass, field
import httpx
import structlog
from jose import jwt, jwk, JWTError
from jose.exceptions import JWKError
from fastapi import Depends, HTTPException, status, Request
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
    Zitadel JWT authentication handler.

    Validates tokens using Zitadel's JWKS (JSON Web Key Set).
    """

    def __init__(self, settings: ZitadelSettings):
        self.settings = settings
        self._jwks: Optional[dict] = None
        self._jwks_fetched_at: Optional[datetime] = None

    async def get_jwks(self) -> dict:
        """
        Fetch and cache JWKS from Zitadel.

        Returns:
            JWKS dictionary with signing keys
        """
        now = datetime.now(timezone.utc)

        # Check if cache is still valid
        if self._jwks and self._jwks_fetched_at:
            cache_age = (now - self._jwks_fetched_at).total_seconds()
            if cache_age < self.settings.jwks_cache_ttl:
                return self._jwks

        # Fetch fresh JWKS
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.settings.jwks_uri,
                    timeout=10.0,
                )
                response.raise_for_status()
                self._jwks = response.json()
                self._jwks_fetched_at = now

                logger.info(
                    "jwks_fetched",
                    issuer=self.settings.issuer,
                    keys_count=len(self._jwks.get("keys", [])),
                )

                return self._jwks

        except httpx.HTTPError as e:
            logger.error("jwks_fetch_failed", error=str(e))
            # Return cached JWKS if available, even if expired
            if self._jwks:
                logger.warning("using_stale_jwks")
                return self._jwks
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to fetch authentication keys",
            )

    def _get_signing_key(self, token: str, jwks: dict) -> Any:
        """
        Get the signing key for a token from JWKS.

        Args:
            token: JWT token string
            jwks: JWKS dictionary

        Returns:
            Signing key for token verification
        """
        try:
            # Get the key ID from token header
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            if not kid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token missing key ID",
                )

            # Find matching key in JWKS
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    return jwk.construct(key)

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token signing key not found",
            )

        except JWKError as e:
            logger.error("jwk_construction_failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signing key",
            )

    async def validate_token(self, token: str) -> dict:
        """
        Validate a JWT token and return claims.

        Args:
            token: JWT access token string

        Returns:
            Token claims dictionary

        Raises:
            HTTPException: If token is invalid
        """
        # Fetch JWKS
        jwks = await self.get_jwks()

        # Get signing key
        signing_key = self._get_signing_key(token, jwks)

        try:
            # Decode and validate token
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                issuer=self.settings.issuer,
                options={
                    "verify_aud": False,  # Zitadel doesn't always set aud
                    "verify_iat": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iss": True,
                    "verify_sub": True,
                },
            )

            logger.debug(
                "token_validated",
                sub=claims.get("sub"),
                exp=claims.get("exp"),
            )

            return claims

        except jwt.ExpiredSignatureError:
            logger.warning("token_expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        except jwt.JWTClaimsError as e:
            logger.warning("token_claims_invalid", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token claims: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )

        except JWTError as e:
            logger.warning("token_invalid", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

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
            full_name=user.name,
            avatar_url=user.picture,
            is_active=True,
            is_verified=user.email_verified,
            oauth_provider="zitadel",
            oauth_id=user.sub,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
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
        # Update user info from Zitadel (in case it changed)
        if db_user.email != user.email or db_user.full_name != user.name:
            db_user.email = user.email
            db_user.full_name = user.name
            db_user.avatar_url = user.picture or db_user.avatar_url
            db_user.updated_at = datetime.now(timezone.utc)
            db.commit()

        # Update last login
        db_user.last_login_at = datetime.now(timezone.utc)
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
