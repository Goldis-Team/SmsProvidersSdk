"""The checks and coercions every provider needs, written once so they cannot drift apart."""

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from sms_providers_sdk.common.constants import REDACTED
from sms_providers_sdk.common.exceptions import ConfigurationError

_ASCII_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
"""Persian (U+06F0…) and Arabic-Indic (U+0660…) digits folded to ASCII.

Numbers typed on a Persian keyboard, or copied out of a Persian PDF, arrive in these code points.
They look identical to ASCII digits in a terminal, so the resulting rejection is one of the harder
ones to see — the number in the log reads correctly and the provider still says 411.
"""

_SEPARATORS = re.compile(r"[\s\-()._]")


def as_int(value: Any) -> int | None:
    """An optional integer field, or ``None`` when the provider omitted it or sent nonsense.

    Result records are descriptive — nothing is decided on them — so a cost that arrives as ``""``
    is reported as missing rather than raising in the middle of parsing a successful send.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_mapping(value: Any) -> dict[str, Any]:
    """A nested JSON object, or an empty dict when the provider sent something else.

    Every provider here reaches into a sub-object it does not control — Kavenegar's ``return``,
    SMS.ir's ``data``, Melipayamak's ``errors``. A bare ``isinstance(value, dict)`` is not enough
    on its own: it proves only that this *is* a dict, so a strict type checker reads it as
    ``dict[Unknown, Unknown]`` and every ``.get()`` off it comes back untyped. Narrowing once here,
    to keys that are known to be strings — which JSON guarantees — is what keeps the rest of each
    provider's parsing typed.

    Returning ``{}`` rather than raising is deliberate: a missing sub-object is read as missing
    fields, which each caller already handles, instead of a parse error at a point where the
    caller cannot say which provider field was wrong.
    """
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def as_sequence(value: Any) -> list[Any]:
    """A nested JSON array, or an empty list when the provider sent something else.

    The list counterpart of :func:`as_mapping`, and there for the same reason. Callers that need
    to tell "the provider sent an empty array" from "the provider sent no array" check the result
    against what they expected — an empty list of message ids is an error to every caller here
    either way.
    """
    if not isinstance(value, list):
        return []
    # The two type checkers disagree about what `isinstance` proved: one narrows to `list[Any]`
    # and calls this cast redundant, the other narrows to `list[Unknown]` and needs it. Dropping
    # the cast only moves the complaint to the other checker, so it stays and the objection is
    # silenced here.
    return cast("list[Any]", value)  # type: ignore[redundant-cast]


def as_decimal(value: Any) -> Decimal | None:
    """An optional money-ish field, or ``None`` when the provider omitted it or sent nonsense.

    Built from ``str(value)`` rather than from the float ``json`` already produced, so a cost of
    ``1.1`` stays ``Decimal("1.1")`` instead of the binary approximation that
    ``Decimal(1.1)`` gives. It is a small difference until costs are summed over a few thousand
    messages and compared against an invoice.
    """
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None


def sum_costs(values: Iterable[Decimal | None]) -> Decimal | None:
    """The total of the costs that were actually reported, or ``None`` when none were.

    A batch where the provider priced only some messages reports what it did price, rather than
    nothing at all — but a batch where it priced nothing reports ``None``, not a misleading zero.
    """
    costs = [value for value in values if value is not None]
    return sum(costs, Decimal(0)) if costs else None


def as_text(value: Any) -> str | None:
    """An optional string field, stripped, or ``None`` when empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_number(value: str) -> str:
    """A phone number in the form Iranian providers expect: ASCII digits, no separators, leading
    zero.

    Folds Persian and Arabic-Indic digits, drops spaces, dashes, dots and brackets, and rewrites
    ``+98…``/``0098…``/``98…`` to ``0…``. Everything else is left alone, because the same field
    also carries short codes and international numbers, and "fixing" those would be guessing.

    The ``98`` prefix is only rewritten for a 12-digit number starting ``989`` — an Iranian mobile
    and nothing else. A short code beginning with those digits is a real line, and turning it into
    a mobile number would send the message somewhere it was never addressed.
    """
    text = _SEPARATORS.sub("", str(value).translate(_ASCII_DIGITS).strip())
    if text.startswith("+98"):
        return "0" + text[3:]
    if text.startswith("0098"):
        return "0" + text[4:]
    if text.startswith("989") and len(text) == 12:
        return "0" + text[2:]
    return text


def check_receptor(value: str, *, provider: str, field: str = "receptor") -> str:
    """A recipient number, normalised, or a :class:`ConfigurationError` saying which one was bad.

    Fails here rather than at the provider. An empty or whitespace-only recipient comes back as a
    bare numeric code — Kavenegar's 411 — with no indication of *which* number in a batch of two
    hundred it objected to.
    """
    number = normalize_number(value)
    if not number:
        raise ConfigurationError(f"{provider} needs a {field}, and {value!r} normalises to empty")
    if not number.lstrip("+").isdigit():
        raise ConfigurationError(f"{provider} got a non-numeric {field}: {value!r}")
    return number


def check_text(value: str, *, provider: str, limit: int | None = None) -> str:
    """A message body that the provider will actually accept.

    Empty text and over-length text are the same provider error (Kavenegar's 413), which makes the
    two indistinguishable from the code alone. Splitting them here means the message says which it
    was, and says it before the request is billed.
    """
    text = str(value or "")
    if not text.strip():
        raise ConfigurationError(f"{provider} was given an empty message")
    if limit is not None and len(text) > limit:
        raise ConfigurationError(
            f"{provider} caps a message at {limit} characters; this one is {len(text)}"
        )
    return text


def check_credential(value: str, *, provider: str, field: str) -> str:
    """A required credential, stripped, or a :class:`ConfigurationError` naming the field.

    Called from the engine constructors so a provider built without its API key fails while the
    application is starting, not on the first message it tries to send.
    """
    text = str(value or "").strip()
    if not text:
        raise ConfigurationError(f"{provider} needs a {field}, and none was set")
    return text


def redact(text: str, secret: str | None) -> str:
    """Replace a credential with :data:`~sms_providers_sdk.common.constants.REDACTED`.

    Providers that authenticate by putting the API key **in the URL** — Kavenegar does — turn every
    client-library error message into a credential leak, because ``requests`` and ``aiohttp`` both
    include the failing URL in the exception they raise. Those messages go straight into logs and
    bug reports. This runs on the way out of the transport, before the text exists anywhere.
    """
    if not secret:
        return text
    return text.replace(secret, REDACTED)
