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
        status_message=as_text(status) if isinstance(status, str) else None,
        rec_ids=tuple(rec_ids),
    )


def _refuse(raw: dict[str, Any]) -> ProviderError:
    reason = (
        _problem_message(raw)
        or read_details(raw).status_message
        or "it reported no message id and gave no reason"
    )
    return ProviderError(f"{NAME} refused the call: {reason}", raw=raw)


def parse_single_response(raw: dict[str, Any], mobile: str) -> SmsResult:
    rec_id = as_text(raw.get("recId"))
    if not rec_id:
        raise _refuse(raw)
    entry = SentMessage(message_id=rec_id, receptor=mobile, raw=raw)
    return SmsResult(messages=(entry,), raw=raw, details=read_details(raw, (rec_id,)))


def parse_advanced_response(raw: dict[str, Any], mobiles: Sequence[str], line: str) -> SmsResult:
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
    return SmsResult(messages=messages, raw=raw, details=read_details(raw, rec_ids))
