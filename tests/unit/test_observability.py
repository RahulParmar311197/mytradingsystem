from packages.observability.logging import safe_context


def test_secrets_are_redacted() -> None:
    assert safe_context({"access_token": "secret-value", "symbol": "NIFTY"}) == {
        "access_token": "[REDACTED]",
        "symbol": "NIFTY",
    }
