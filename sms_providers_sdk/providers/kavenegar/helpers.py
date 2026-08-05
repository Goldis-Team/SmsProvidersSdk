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
    as_decimal,
    as_int,
    as_mapping,
    as_sequence,
    as_text,
    check_receptor,
    check_text,
    sum_costs,
)
from sms_providers_sdk.providers.kavenegar.constants import (
    BASE_URL,
    MAX_MESSAGE_LENGTH,
    MAX_RECIPIENTS,
    MAX_TOKEN_LENGTH,
    MAX_TOKENS,
    MESSAGE_STATUSES,
    NAME,
    RETURN_STATUSES,
    SPACES_ALLOWED_IN,
    SUCCESS_STATUS,
)
from sms_providers_sdk.providers.kavenegar.data import KavenegarConfig, KavenegarDetails


def endpoint(config: KavenegarConfig, scope: str, method: str) -> str:
    return BASE_URL.format(api_key=quote(config.api_key, safe=""), scope=scope, method=method)


def _line(config: KavenegarConfig, sender: str, *, operation: str) -> str:
    line = (sender or config.sender).strip()
    if not line:
        raise ConfigurationError(
            f"{NAME} requires a sending line on {operation} — pass sender=… when building the "
            f"provider, or on the message"
        )
    return line


def _common_fields(payload: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    payload.update(extra)
    return payload


def build_send_payload(config: KavenegarConfig, message: SmsMessage) -> dict[str, Any]:
    """``sms/send`` for a single recipient."""
    payload: dict[str, Any] = {
        "receptor": check_receptor(message.receptor, provider=NAME),
        "message": check_text(message.text, provider=NAME, limit=MAX_MESSAGE_LENGTH),
    }
    payload["sender"] = _line(config, message.sender, operation="a send")
    if message.send_at is not None:
        payload["date"] = int(message.send_at)
    if message.local_id:
        payload["localid"] = message.local_id
    return _common_fields(payload, message.extra)


def build_bulk_payload(config: KavenegarConfig, message: BulkSmsMessage) -> dict[str, Any]:
    numbers = [check_receptor(number, provider=NAME) for number in message.receptors]
    if not numbers:
        raise ConfigurationError(f"{NAME} was given an empty recipient list")
    if len(numbers) > MAX_RECIPIENTS:
        raise ConfigurationError(
            f"{NAME} takes at most {MAX_RECIPIENTS} recipients per call; this batch has "
            f"{len(numbers)} — split it, because Kavenegar rejects an oversized batch whole and "
            f"none of the messages go out"
        )
    payload: dict[str, Any] = {
        "receptor": ",".join(numbers),
        "message": check_text(message.text, provider=NAME, limit=MAX_MESSAGE_LENGTH),
    }
    payload["sender"] = _line(config, message.sender, operation="a bulk send")
    if message.send_at is not None:
        payload["date"] = int(message.send_at)
    if message.local_ids:
        local_ids = list(message.local_ids)
        if len(local_ids) != len(numbers):
            raise ConfigurationError(
                f"{NAME} pairs local ids to recipients by position: got {len(local_ids)} ids for "
                f"{len(numbers)} recipients, which would attach them to the wrong numbers"
            )
        payload["localid"] = ",".join(str(local_id) for local_id in local_ids)
    return _common_fields(payload, message.extra)


def token_fields(tokens: Sequence[str] | Mapping[str, str]) -> dict[str, str]:
    if isinstance(tokens, Mapping):
        fields = {str(key): str(value) for key, value in tokens.items()}
    else:
        values = list(tokens)
        if len(values) > MAX_TOKENS:
            raise ConfigurationError(
                f"{NAME} templates take at most {MAX_TOKENS} tokens; got {len(values)}"
            )
        fields = {
            ("token" if index == 0 else f"token{index + 1}"): str(value)
            for index, value in enumerate(values)
        }
    for name, value in fields.items():
        if len(value) > MAX_TOKEN_LENGTH:
            raise ConfigurationError(
                f"{NAME} caps {name} at {MAX_TOKEN_LENGTH} characters; this one is {len(value)}"
            )
        if name not in SPACES_ALLOWED_IN and any(char.isspace() for char in value):
            raise ConfigurationError(
                f"{NAME} rejects whitespace in {name} ({value!r}) — only "
                f"{' and '.join(sorted(SPACES_ALLOWED_IN))} accept it. Use a zero-width "
                f"non-joiner or a dash, or move this value to one of those slots"
            )
    return fields


def build_pattern_payload(config: KavenegarConfig, message: PatternMessage) -> dict[str, Any]:
    if message.sender:
        raise ConfigurationError(
            f"{NAME} pattern sends have no sender parameter — the line is fixed by the "
            f"{message.pattern!r} template. Remove sender, or change the template's line in the "
            f"panel"
        )
    template = str(message.pattern or "").strip()
    if not template:
        raise ConfigurationError(f"{NAME} needs a template name for a pattern send")
    payload: dict[str, Any] = {
        "receptor": check_receptor(message.receptor, provider=NAME),
        "template": template,
    }
    payload.update(token_fields(message.tokens))
    return _common_fields(payload, message.extra)


def read_details(raw: dict[str, Any]) -> KavenegarDetails:
    """The ``return`` object: what Kavenegar said about the call as a whole."""
    envelope = as_mapping(raw.get("return"))
    status = as_int(envelope.get("status"))
    return KavenegarDetails(
        return_status=status,
        return_message=as_text(envelope.get("message")),
        status_description=RETURN_STATUSES.get(status) if status is not None else None,
    )


def read_entries(raw: dict[str, Any]) -> tuple[SentMessage, ...]:
    entries = raw.get("entries")
    listed = [as_mapping(entries)] if isinstance(entries, dict) else as_sequence(entries)
    messages: list[SentMessage] = []
    for entry in listed:
        item = as_mapping(entry)
        if not item:
            continue
        status = as_int(item.get("status"))
        messages.append(
            SentMessage(
                message_id=as_text(item.get("messageid")) or "",
                receptor=as_text(item.get("receptor")) or "",
                status=status,
                status_text=(
                    as_text(item.get("statustext"))
                    or (MESSAGE_STATUSES.get(status) if status is not None else None)
                ),
                sender=as_text(item.get("sender")),
                text=as_text(item.get("message")),
                cost=as_decimal(item.get("cost")),
                sent_at=as_int(item.get("date")),
                local_id=as_text(item.get("localid")),
                raw=item,
            )
        )
    return tuple(messages)


def parse_response(raw: dict[str, Any]) -> SmsResult:
    details = read_details(raw)
    if details.return_status != SUCCESS_STATUS:
        reason = (
            details.status_description
            or details.return_message
            or f"status {details.return_status}"
        )
        raise ProviderError(
            f"{NAME} refused the call: {reason}", code=details.return_status, raw=raw
        )
    messages = read_entries(raw)
    if not messages:
        raise ProviderError(
            f"{NAME} accepted the call but reported no messages — nothing was sent",
            code=details.return_status,
            raw=raw,
        )
    return SmsResult(
        messages=messages,
        cost=sum_costs(entry.cost for entry in messages),
        raw=raw,
        details=details,
    )
