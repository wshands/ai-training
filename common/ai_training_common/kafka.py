"""Kafka connection helpers shared across services."""

from __future__ import annotations

import os
import re
import ssl
import time
from typing import Any, Dict

from aiokafka.abc import AbstractTokenProvider

from common.ai_training_common.config import (
    KAFKA_BOOTSTRAP,
    KAFKA_SECURITY_PROTOCOL,
    KAFKA_SASL_MECHANISM,
    KAFKA_SASL_USERNAME,
    KAFKA_SASL_PASSWORD,
    KAFKA_SSL_CA_FILE,
    KAFKA_SSL_CERT_FILE,
    KAFKA_SSL_KEY_FILE,
)


def build_kafka_config() -> Dict[str, Any]:
    """Build aiokafka-compatible connection settings from env vars."""
    bootstrap_servers = [s.strip() for s in KAFKA_BOOTSTRAP.split(",") if s.strip()]
    config: Dict[str, Any] = {
        "bootstrap_servers": bootstrap_servers,
    }

    raw_mechanism = (KAFKA_SASL_MECHANISM or "").upper()
    # Treat explicit OAUTHBEARER as MSK IAM when no custom provider is configured.
    msk_iam_enabled = raw_mechanism in ("AWS_MSK_IAM", "OAUTHBEARER")

    if KAFKA_SECURITY_PROTOCOL:
        config["security_protocol"] = KAFKA_SECURITY_PROTOCOL

    if KAFKA_SASL_MECHANISM:
        if msk_iam_enabled:
            config["sasl_mechanism"] = "OAUTHBEARER"
        else:
            config["sasl_mechanism"] = KAFKA_SASL_MECHANISM

    if KAFKA_SASL_USERNAME and not msk_iam_enabled:
        config["sasl_plain_username"] = KAFKA_SASL_USERNAME

    if KAFKA_SASL_PASSWORD and not msk_iam_enabled:
        config["sasl_plain_password"] = KAFKA_SASL_PASSWORD

    ssl_context = None
    if KAFKA_SSL_CA_FILE or KAFKA_SSL_CERT_FILE or KAFKA_SSL_KEY_FILE:
        ssl_context = ssl.create_default_context(cafile=KAFKA_SSL_CA_FILE or None)
        if KAFKA_SSL_CERT_FILE and KAFKA_SSL_KEY_FILE:
            ssl_context.load_cert_chain(KAFKA_SSL_CERT_FILE, KAFKA_SSL_KEY_FILE)
    elif (KAFKA_SECURITY_PROTOCOL or "").upper() in ("SSL", "SASL_SSL"):
        # Use system CA bundle when SSL is required but no custom certs are provided.
        ssl_context = ssl.create_default_context()

    if ssl_context:
        config["ssl_context"] = ssl_context

    if msk_iam_enabled:
        region = _resolve_region(bootstrap_servers)
        if not region:
            raise RuntimeError("AWS region not found for MSK IAM auth. Set AWS_REGION or AWS_DEFAULT_REGION.")
        config.setdefault("security_protocol", "SASL_SSL")
        if "ssl_context" not in config:
            config["ssl_context"] = ssl.create_default_context()
        config["sasl_oauth_token_provider"] = _MskIamTokenProvider(region)

    return config


def _resolve_region(bootstrap_servers: list[str]) -> str:
    env_region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if env_region:
        return env_region
    if not bootstrap_servers:
        return ""
    host = bootstrap_servers[0].split(":")[0]
    match = re.search(r"\.(?P<region>[a-z]{2}-[a-z]+-\d)\.amazonaws\.com$", host)
    return match.group("region") if match else ""


class _MskIamTokenProvider(AbstractTokenProvider):
    def __init__(self, region: str, refresh_margin_seconds: int = 60) -> None:
        self._region = region
        self._refresh_margin_seconds = refresh_margin_seconds
        self._token: str | None = None
        self._expires_at: float = 0.0

    async def token(self) -> str:
        now = time.time()
        if self._token and now < (self._expires_at - self._refresh_margin_seconds):
            return self._token

        token, expires_at = _generate_msk_iam_token(self._region)
        self._token = token
        self._expires_at = expires_at or (now + 15 * 60)
        return token


def _generate_msk_iam_token(region: str) -> tuple[str, float | None]:
    try:
        from aws_msk_iam_sasl_signer import MSKAuthTokenProvider  # type: ignore

        token, expiry_ms = MSKAuthTokenProvider.generate_auth_token(region)
        expiry_seconds = (expiry_ms / 1000.0) if expiry_ms else None
        return token, expiry_seconds
    except ImportError:
        try:
            from aws_msk_iam_sasl_signer import generate_auth_token  # type: ignore

            token, expiry_ms = generate_auth_token(region)
            expiry_seconds = (expiry_ms / 1000.0) if expiry_ms else None
            return token, expiry_seconds
        except ImportError as exc:
            raise RuntimeError(
                "aws-msk-iam-sasl-signer is required for AWS_MSK_IAM auth. "
                "Add it to requirements and rebuild the image."
            ) from exc
