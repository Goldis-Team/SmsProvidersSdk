"""The checks and coercions every provider needs, written once so they cannot drift apart."""

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from sms_providers_sdk.common.constants import REDACTED
from sms_providers_sdk.common.exceptions import ConfigurationError

_ASCII_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_SEPARATORS = re.compile(r"[\s\-()._]")


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_mapping(value: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def as_sequence(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return cast("list[Any]", value)  # type: ignore[redundant-cast]


def as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None


def sum_costs(values: Iterable[Decimal | None]) -> Decimal | None:
    costs = [value for value in values if value is not None]
    return sum(costs, Decimal(0)) if costs else None


def as_text(value: Any) -> str | None:
    """An optional string field, stripped, or ``None`` when empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_number(value: str) -> str:
    text = _SEPARATORS.sub("", str(value).translate(_ASCII_DIGITS).strip())
    if text.startswith("+98"):
        return "0" + text[3:]
    if text.startswith("0098"):
        return "0" + text[4:]
    if text.startswith("989") and len(text) == 12:
        return "0" + text[2:]
    return text


def check_receptor(value: str, *, provider: str, field: str = "receptor") -> str:
    number = normalize_number(value)
    if not number:
        raise ConfigurationError(f"{provider} needs a {field}, and {value!r} normalises to empty")
    if not number.lstrip("+").isdigit():
        raise ConfigurationError(f"{provider} got a non-numeric {field}: {value!r}")
    return number


def check_text(value: str, *, provider: str, limit: int | None = None) -> str:
    text = str(value or "")
    if not text.strip():
        raise ConfigurationError(f"{provider} was given an empty message")
    if limit is not None and len(text) > limit:
        raise ConfigurationError(
            f"{provider} caps a message at {limit} characters; this one is {len(text)}"
        )
    return text


def check_credential(value: str, *, provider: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ConfigurationError(f"{provider} needs a {field}, and none was set")
    return text


def redact(text: str, secret: str | None) -> str:
    if not secret:
        return text
    return text.replace(secret, REDACTED)
