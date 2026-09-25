from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from packages.auth import (
    AuthenticationError,
    AuthenticationUnavailable,
    AuthorizationError,
    Role,
    TokenAuthenticator,
)
from packages.config import Settings

VIEWER = "viewer-token-that-is-at-least-32-characters"
OPERATOR = "operator-token-that-is-at-least-32-characters"
PREVIOUS = "previous-token-that-is-at-least-32-characters"


def test_authenticator_recognizes_roles_and_operator_inherits_viewer_access() -> None:
    authenticator = TokenAuthenticator(viewer_token=VIEWER, operator_token=OPERATOR)
    viewer = authenticator.authenticate(f"Bearer {VIEWER}")
    operator = authenticator.authenticate(f"bearer {OPERATOR}")
    assert viewer.role is Role.VIEWER
    assert operator.role is Role.OPERATOR
    assert viewer.credential_sha256 == sha256(VIEWER.encode()).hexdigest()
    assert authenticator.require(viewer, Role.VIEWER) == viewer
    assert authenticator.require(operator, Role.VIEWER) == operator
    assert authenticator.require(operator, Role.OPERATOR) == operator
    with pytest.raises(AuthorizationError):
        authenticator.require(viewer, Role.OPERATOR)


@pytest.mark.parametrize("header", (None, "", "Basic token", "Bearer", "Bearer a b", "Bearer bad"))
def test_authenticator_rejects_missing_or_invalid_credentials(header: str | None) -> None:
    authenticator = TokenAuthenticator(viewer_token=VIEWER, operator_token=OPERATOR)
    with pytest.raises(AuthenticationError):
        authenticator.authenticate(header)


def test_authenticator_fails_closed_when_tokens_are_not_configured() -> None:
    with pytest.raises(AuthenticationUnavailable):
        TokenAuthenticator(viewer_token=None, operator_token=None).authenticate(f"Bearer {VIEWER}")


def test_settings_reject_short_or_reused_api_tokens() -> None:
    with pytest.raises(ValueError, match="32 characters"):
        Settings(api_viewer_token="x" * 10)
    with pytest.raises(ValueError, match="distinct"):
        Settings(api_viewer_token=VIEWER, api_operator_token=VIEWER)


def test_previous_token_is_accepted_only_before_aware_rotation_deadline() -> None:
    future = datetime.now(UTC) + timedelta(hours=1)
    authenticator = TokenAuthenticator(
        viewer_token=VIEWER,
        operator_token=OPERATOR,
        previous_viewer_token=PREVIOUS,
        previous_tokens_expire_at=future,
    )
    assert authenticator.authenticate(f"Bearer {PREVIOUS}").role is Role.VIEWER
    expired = TokenAuthenticator(
        viewer_token=VIEWER,
        operator_token=OPERATOR,
        previous_viewer_token=PREVIOUS,
        previous_tokens_expire_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    with pytest.raises(AuthenticationError):
        expired.authenticate(f"Bearer {PREVIOUS}")


def test_previous_tokens_require_an_aware_expiry() -> None:
    with pytest.raises(ValueError, match="require an expiry"):
        TokenAuthenticator(
            viewer_token=VIEWER,
            operator_token=OPERATOR,
            previous_viewer_token=PREVIOUS,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        Settings(
            api_previous_viewer_token=PREVIOUS,
            api_previous_tokens_expire_at=datetime(2026, 9, 20),
        )


def test_revoked_current_or_previous_tokens_fail_authentication() -> None:
    revoked = sha256(VIEWER.encode()).hexdigest()
    authenticator = TokenAuthenticator(
        viewer_token=VIEWER,
        operator_token=OPERATOR,
        previous_viewer_token=PREVIOUS,
        previous_tokens_expire_at=datetime.now(UTC) + timedelta(hours=1),
        revoked_token_sha256=(revoked, sha256(PREVIOUS.encode()).hexdigest()),
    )
    with pytest.raises(AuthenticationError):
        authenticator.authenticate(f"Bearer {VIEWER}")
    with pytest.raises(AuthenticationError):
        authenticator.authenticate(f"Bearer {PREVIOUS}")
    assert authenticator.authenticate(f"Bearer {OPERATOR}").role is Role.OPERATOR


def test_revocation_digests_are_strictly_validated() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        TokenAuthenticator(
            viewer_token=VIEWER,
            operator_token=OPERATOR,
            revoked_token_sha256=("not-a-digest",),
        )
    digest = sha256(VIEWER.encode()).hexdigest()
    with pytest.raises(ValueError, match="unique"):
        Settings(api_revoked_token_sha256=[digest, digest])
