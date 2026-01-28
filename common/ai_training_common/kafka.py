"""Kafka connection helpers shared across services."""

from __future__ import annotations

import ssl
from typing import Any, Dict

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
    config: Dict[str, Any] = {
        "bootstrap_servers": KAFKA_BOOTSTRAP.split(","),
    }

    if KAFKA_SECURITY_PROTOCOL:
        config["security_protocol"] = KAFKA_SECURITY_PROTOCOL

    if KAFKA_SASL_MECHANISM:
        config["sasl_mechanism"] = KAFKA_SASL_MECHANISM

    if KAFKA_SASL_USERNAME:
        config["sasl_plain_username"] = KAFKA_SASL_USERNAME

    if KAFKA_SASL_PASSWORD:
        config["sasl_plain_password"] = KAFKA_SASL_PASSWORD

    ssl_context = None
    if KAFKA_SSL_CA_FILE or KAFKA_SSL_CERT_FILE or KAFKA_SSL_KEY_FILE:
        ssl_context = ssl.create_default_context(cafile=KAFKA_SSL_CA_FILE or None)
        if KAFKA_SSL_CERT_FILE and KAFKA_SSL_KEY_FILE:
            ssl_context.load_cert_chain(KAFKA_SSL_CERT_FILE, KAFKA_SSL_KEY_FILE)

    if ssl_context:
        config["ssl_context"] = ssl_context

    return config
