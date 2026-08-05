"""Melipayamak — payload building and response reading.

Everything that decides what Melipayamak was asked and what it answered lives here, so the sync and
async engines are thin shells over the same logic and cannot drift apart.
"""

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

from sms_providers_sdk.common.data import (
    BulkSmsMessage,
    PatternMessage,
    SentMessage,
    SmsMessage,
    SmsResult,
)
from sms_providers_sdk.common.exceptions import ConfigurationError, ProviderError
from sms_providers_sdk.common.utils import (
    as_mapping,
    as_sequence,
    as_text,
    check_receptor,
    check_text,
)
from sms_providers_sdk.providers.melipayamak.constants import (
    BASE_URL,
    MAX_BODY_ID,
    NAME,
    PROBLEM_ERRORS_KEY,
    PROBLEM_TITLE_KEY,
)
from sms_providers_sdk.providers.melipayamak.data import MelipayamakConfig, MelipayamakDetails


def endpoint(config: MelipayamakConfig, path: str) -> str:
    """The URL for one console method, with the API key as its last path segment.

    The key is percent-encoded so that a key pasted with a stray character cannot change the
    *path* being requested — and Melipayamak answers an unmatched path with HTTP 200 and the
    console's HTML, which would otherwise surface as a baffling parse error rather than as a bad
    credential.
    """
    return f"{BASE_URL}{path.format(api_key=quote(config.api_key, safe=''))}"


def _line(config: MelipayamakConfig, sender: str, *, operation: str) -> str:
    """The sending line. Required, with no server-side default to fall back on."""
    line = (sender or config.sender).strip()
    if not line:
        raise ConfigurationError(
            f"{NAME} requires a sending line on {operation} — pass sender=… when building the "
            f"provider, or on the message"
        )
    return line


def _reject_unsupported(send_at: int | None, local_id: object, *, field: str = "local_id") -> None:
    """Refuse the two inputs Melipayamak's send endpoints have nowhere to put.

    Neither is dropped silently. Scheduling lives on a separate ``send/schedule`` method that this
    SDK does not wrap, so a ``send_at`` that vanished here would send the message *immediately* —
    the one failure mode a caller scheduling a message would never think to check for.
    """
    if send_at is not None:
        raise ConfigurationError(
            f"{NAME}'s send endpoints take no send time — scheduling is a separate "
            f"send/schedule method this SDK does not wrap. Accepting send_at here would send the "
            f"message immediately instead"
        )
    if local_id:
        raise ConfigurationError(
            f"{NAME} has no client-supplied message id; it returns its own recId. Drop {field}"
        )


def build_simple_payload(config: MelipayamakConfig, message: SmsMessage) -> dict[str, Any]:
    """``send/simple`` — ``{from, to, text}``, all three required."""
    _reject_unsupported(message.send_at, message.local_id)
    payload: dict[str, Any] = {
        "from": _line(config, message.sender, operation="a simple send"),
        "to": check_receptor(message.receptor, provider=NAME),
        "text": check_text(message.text, provider=NAME),
    }
    payload.update(message.extra)
    return payload


def build_advanced_payload(config: MelipayamakConfig, message: BulkSmsMessage) -> dict[str, Any]:
    """``send/advanced`` — one text, one line, a real array of recipients.

    No recipient cap is enforced. Melipayamak documents none for this endpoint, and inventing one
    would refuse batches the account is entitled to send; the other two providers are capped here
    only because their own documentation states the number. If Melipayamak has a limit, its own
    error is the accurate one.
    """
    _reject_unsupported(message.send_at, message.local_ids, field="local_ids")
    numbers = [check_receptor(number, provider=NAME) for number in message.receptors]
    if not numbers:
        raise ConfigurationError(f"{NAME} was given an empty recipient list")
    payload: dict[str, Any] = {
        "from": _line(config, message.sender, operation="a bulk send"),
        "to": numbers,
        "text": check_text(message.text, provider=NAME),
    }
    payload.update(message.extra)
    return payload


def argument_list(tokens: Sequence[str] | Mapping[str, str]) -> list[str]:
    """The template's values as Melipayamak's ``args`` array.

    Positional, and positional only. Melipayamak's ``args`` is a bare ``String[]`` filled in order,
    with no names anywhere in the request — so a mapping has nothing to bind to. Its keys would
    have to be dropped and its values sent in whatever order the dict happened to be in, which is
    an ordering the caller never chose and cannot see; the values would land in the wrong
    placeholders of a message that has already gone out.

    This is the mirror of SMS.ir, which is named-only. There is no token form that is portable
    across all three providers — see the provider table in the README.
    """
    if isinstance(tokens, Mapping):
        raise ConfigurationError(
            f"{NAME} templates take positional arguments, not named ones — its args field is a "
            f'bare array filled in order. Pass a sequence, e.g. tokens=["12345"]'
        )
    return [str(value) for value in tokens]


def build_shared_payload(message: PatternMessage) -> dict[str, Any]:
    """``send/shared`` — ``{bodyId, to, args}``. No line: the template owns it."""
    if message.sender:
        raise ConfigurationError(
            f"{NAME} pattern sends have no line parameter — the line is fixed by template "
            f"{message.pattern!r}. Remove sender, or change the template's line in the panel"
        )
    body_id = str(message.pattern or "").strip()
    if not body_id.isdigit():
        raise ConfigurationError(
            f"{NAME} identifies templates by numeric bodyId, not by name; got {message.pattern!r}"
        )
    if int(body_id) > MAX_BODY_ID:
        raise ConfigurationError(
            f"{NAME} declares bodyId as a 32-bit integer; {body_id} is larger than {MAX_BODY_ID}"
        )
    payload: dict[str, Any] = {
        "bodyId": int(body_id),
        "to": check_receptor(message.receptor, provider=NAME),
        "args": argument_list(message.tokens),
    }
    payload.update(message.extra)
    return payload


def _problem_message(raw: dict[str, Any]) -> str | None:
    """The message from an RFC 7807 ProblemDetails body, or ``None`` if this is not one.

    This is what ASP.NET Core's model binder answers *before* Melipayamak's own code runs, so it
    describes a malformed request rather than a refused one. Its ``status`` is the integer 400,
    which is why it has to be recognised: reading that field as text would report the failure as
    ``"400"`` and throw away the ``errors`` object that says which field was wrong.
    """
    errors = as_mapping(raw.get(PROBLEM_ERRORS_KEY))
    title = raw.get(PROBLEM_TITLE_KEY)
    titled = isinstance(title, str) and isinstance(raw.get("status"), int)
    if not errors and not titled:
        return None
    details: list[str] = []
    for field, problems in errors.items():
        if isinstance(problems, list):
            details.extend(f"{field}: {problem}" for problem in as_sequence(problems))
        else:
            details.append(f"{field}: {problems}")
    headline = title if isinstance(title, str) else "the request was rejected as malformed"
    return f"{headline} ({'; '.join(details)})" if details else headline


def read_details(raw: dict[str, Any], rec_ids: Sequence[str] = ()) -> MelipayamakDetails:
    """What Melipayamak said about the call as a whole."""
    status = raw.get("status")
    return MelipayamakDetails(
        # Only a string `status` is Melipayamak's own message; an int one belongs to the
        # ProblemDetails shape and is an HTTP status, not something it said.
        status_message=as_text(status) if isinstance(status, str) else None,
        rec_ids=tuple(rec_ids),
    )


def _refuse(raw: dict[str, Any]) -> ProviderError:
    """The error for a response that carried no id.

    ``code`` is ``None`` and stays that way: Melipayamak reports failures as Persian sentences, not
    as numbers, so there is nothing to branch on and pretending otherwise — by inventing codes, or
    by passing the HTTP status off as one — would give callers something to switch on that this
    provider never promised to keep stable.
    """
    reason = (
        _problem_message(raw)
        or read_details(raw).status_message
        or "it reported no message id and gave no reason"
    )
    return ProviderError(f"{NAME} refused the call: {reason}", raw=raw)


def parse_single_response(raw: dict[str, Any], mobile: str) -> SmsResult:
    """``send/simple`` and ``send/shared``: one recipient, so one id.

    Success is the id being present. ``status`` is documented only as an error description, and
    what it holds on a successful send is not specified — so nothing here compares it against
    anything.
    """
    rec_id = as_text(raw.get("recId"))
    if not rec_id:
        raise _refuse(raw)
    entry = SentMessage(message_id=rec_id, receptor=mobile, raw=raw)
    return SmsResult(messages=(entry,), raw=raw, details=read_details(raw, (rec_id,)))


def parse_advanced_response(raw: dict[str, Any], mobiles: Sequence[str], line: str) -> SmsResult:
    """``send/advanced``: one id per recipient, in the order the numbers were submitted.

    Melipayamak's own example pairs two recipients with two ids in order, but no source states the
    length-and-order guarantee outright. So the numbers are paired back only when the counts match;
    otherwise the recipients are left blank rather than guessed, because an id attributed to the
    wrong number is worse than one attributed to nobody.
    """
    rec_ids = [text for text in (as_text(item) for item in as_sequence(raw.get("recIds"))) if text]
    if not rec_ids:
        raise _refuse(raw)
    paired = len(rec_ids) == len(mobiles)
    messages = tuple(
        SentMessage(
            message_id=rec_id,
            receptor=mobiles[index] if paired else "",
            sender=line,
            raw={"recId": rec_id},
        )
        for index, rec_id in enumerate(rec_ids)
    )
    # Melipayamak reports no cost on either send endpoint — credit is a separate call.
    return SmsResult(messages=messages, raw=raw, details=read_details(raw, rec_ids))
