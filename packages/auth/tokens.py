"""Constant-time bearer-token authentication with a deliberately small role model."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from hmac import compare_digest


class Role(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    role: Role
    credential_sha256: str


class AuthenticationError(ValueError):
    pass


class AuthenticationUnavailable(RuntimeError):
    pass


class AuthorizationError(PermissionError):
    pass


class TokenAuthenticator:
    """Authenticate configured opaque tokens without retaining their plaintext values."""

    def __init__(
        self,
        *,
        viewer_token: str | None,
        operator_token: str | None,
        previous_viewer_token: str | None = None,
        previous_operator_token: str | None = None,
        previous_tokens_expire_at: datetime | None = None,
        revoked_token_sha256: tuple[str, ...] = (),
    ) -> None:
        if previous_tokens_expire_at is not None and (
            previous_tokens_expire_at.tzinfo is None
            or previous_tokens_expire_at.utcoffset() is None
        ):
            raise ValueError("previous-token expiry must be timezone-aware")
        if (previous_viewer_token is not None or previous_operator_token is not None) and (
            previous_tokens_expire_at is None
        ):
            raise ValueError("previous tokens require an expiry")
        tokens = (
            (Role.VIEWER, viewer_token, None),
            (Role.OPERATOR, operator_token, None),
            (Role.VIEWER, previous_viewer_token, previous_tokens_expire_at),
            (Role.OPERATOR, previous_operator_token, previous_tokens_expire_at),
        )
        self._digests = tuple(
            (role, sha256(token.encode()).digest(), expires_at)
            for role, token, expires_at in tokens
            if token is not None
        )
        digests = tuple(digest for _, digest, _ in self._digests)
        if len(digests) != len(set(digests)):
            raise ValueError("bearer tokens must be distinct")
        if len(revoked_token_sha256) != len(set(revoked_token_sha256)) or any(
            len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
            for digest in revoked_token_sha256
        ):
            raise ValueError("revoked token digests must be unique lowercase SHA-256 values")
        self._revoked_digests = tuple(bytes.fromhex(digest) for digest in revoked_token_sha256)

    def authenticate(self, authorization: str | None) -> Principal:
        if not self._digests:
            raise AuthenticationUnavailable("API authentication is not configured")
        if authorization is None:
            raise AuthenticationError("bearer authorization is required")
        scheme, separator, token = authorization.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token or " " in token:
            raise AuthenticationError("bearer authorization is invalid")
        candidate = sha256(token.encode()).digest()
        matched_role: Role | None = None
        matched_expiry: datetime | None = None
        for role, digest, expires_at in self._digests:
            if compare_digest(candidate, digest):
                matched_role = role
                matched_expiry = expires_at
        revoked = False
        for digest in self._revoked_digests:
            if compare_digest(candidate, digest):
                revoked = True
        if (
            matched_role is None
            or (matched_expiry is not None and datetime.now(UTC) >= matched_expiry)
            or revoked
        ):
            raise AuthenticationError("bearer authorization is invalid")
        return Principal(f"api:{matched_role.value}", matched_role, candidate.hex())

    @staticmethod
    def require(principal: Principal, role: Role) -> Principal:
        allowed = principal.role is Role.OPERATOR or principal.role is role
        if not allowed:
            raise AuthorizationError(f"{role.value} role is required")
        return principal
