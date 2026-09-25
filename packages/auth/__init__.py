"""Authentication and role-based authorization primitives."""

from packages.auth.persistence import PersistentTokenRevocationStore
from packages.auth.tokens import (
    AuthenticationError,
    AuthenticationUnavailable,
    AuthorizationError,
    Principal,
    Role,
    TokenAuthenticator,
)

__all__ = [
    "AuthenticationError",
    "AuthenticationUnavailable",
    "AuthorizationError",
    "PersistentTokenRevocationStore",
    "Principal",
    "Role",
    "TokenAuthenticator",
]
