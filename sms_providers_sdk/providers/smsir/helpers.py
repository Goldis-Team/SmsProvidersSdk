from collections.abc import Mapping, Sequence
from typing import Any

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
)
from sms_providers_sdk.providers.smsir.constants import (
    API_KEY_HEADER,
    BASE_URL,
    MAX_PARAMETER_LENGTH,
    MAX_RECIPIENTS,
    NAME,
    STATUSES,
    SUCCESS_STATUS,
)
from sms_providers_sdk.providers.smsir.data import SmsIrConfig, SmsIrDetails


def endpoint(path: str) -> str:
    """The URL for one SMS.ir method. No credential in it — that goes in a header."""
    return f"{BASE_URL}{path}"


def auth_headers(config: SmsIrConfig) -> dict[str, str]:
    return {API_KEY_HEADER: config.api_key}


def check_line(config: SmsIrConfig, sender: str) -> int:
    line = (sender or config.line_number).strip()
    if not line:
        raise ConfigurationError(
            f"{NAME} needs a line number on every send and has no account default — pass "
            f"line_number=… when building the provider, or sender=… on the message"
        )
    if not line.isdigit():
        raise ConfigurationError(f"{NAME} needs a numeric line number; got {line!r}")
    return int(line)


def _mobiles(receptors: Sequence[str]) -> list[str]:
    numbers = [check_receptor(number, provider=NAME) for number in receptors]
    if not numbers:
        raise ConfigurationError(f"{NAME} was given an empty recipient list")
    if len(numbers) > MAX_RECIPIENTS:
        raise ConfigurationError(
            f"{NAME} takes at most {MAX_RECIPIENTS} recipients per call; this batch has "
            f"{len(numbers)} — split it, because SMS.ir rejects an oversized batch whole and none "
            f"of the messages go out"
        )
    return numbers


def build_single_payload(config: SmsIrConfig, message: SmsMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "lineNumber": check_line(config, message.sender),
        "messageText": check_text(message.text, provider=NAME),
        "mobiles": [check_receptor(message.receptor, provider=NAME)],
    }
    if message.send_at is not None:
        payload["sendDateTime"] = int(message.send_at)
    payload.update(message.extra)
    return payload


def build_bulk_payload(config: SmsIrConfig, message: BulkSmsMessage) -> dict[str, Any]:
    if message.local_ids:
        raise ConfigurationError(
            f"{NAME} has no client-supplied message id — it assigns a packId instead, which comes "
            f"back on result.details.pack_id. Drop local_ids"
        )
    payload: dict[str, Any] = {
        "lineNumber": check_line(config, message.sender),
        "messageText": check_text(message.text, provider=NAME),
        "mobiles": _mobiles(message.receptors),
    }
    if message.send_at is not None:
        payload["sendDateTime"] = int(message.send_at)
    payload.update(message.extra)
    return payload


def parameter_list(tokens: Sequence[str] | Mapping[str, str]) -> list[dict[str, str]]:
    if not isinstance(tokens, Mapping):
        if not tokens:
            return []
        raise ConfigurationError(
            f"{NAME} templates take named parameters, not positional ones — its placeholders are "
            f"#NAME# and the API matches on the name. Pass a mapping, e.g. "
            f'tokens={{"CODE": "12345"}}'
        )
    parameters: list[dict[str, str]] = []
    for name, value in tokens.items():
        clean_name = str(name).strip()
        if not clean_name:
            raise ConfigurationError(f"{NAME} rejects an empty parameter name")
        text = str(value)
        if len(text) > MAX_PARAMETER_LENGTH:
            raise ConfigurationError(
                f"{NAME} caps a parameter value at {MAX_PARAMETER_LENGTH} characters; "
                f"{clean_name} is {len(text)}"
            )
        parameters.append({"name": clean_name, "value": text})
    return parameters


def build_pattern_payload(config: SmsIrConfig, message: PatternMessage) -> dict[str, Any]:
    if message.sender:
        raise ConfigurationError(
            f"{NAME} pattern sends have no line parameter — the line is fixed by template "
            f"{message.pattern!r}. Remove sender, or change the template's line in the panel"
        )
    template = str(message.pattern or "").strip()
    if not template.isdigit():
        raise ConfigurationError(
            f"{NAME} identifies templates by numeric id, not by name; got {message.pattern!r}. "
            f"The id is shown next to the template in the panel"
        )
    payload: dict[str, Any] = {
        "mobile": check_receptor(message.receptor, provider=NAME),
        "templateId": int(template),
        "parameters": parameter_list(message.tokens),
    }
    payload.update(message.extra)
    return payload


def read_details(raw: dict[str, Any]) -> SmsIrDetails:
    """What SMS.ir said about the call as a whole."""
    status = as_int(raw.get("status"))
    data = as_mapping(raw.get("data"))
    return SmsIrDetails(
        status=status,
        status_message=as_text(raw.get("message")),
        status_description=STATUSES.get(status) if status is not None else None,
        pack_id=as_text(data.get("packId")),
    )


def accepted_data(raw: dict[str, Any]) -> tuple[SmsIrDetails, dict[str, Any]]:
    details = read_details(raw)
    if details.status != SUCCESS_STATUS:
        reason = details.status_description or details.status_message or f"status {details.status}"
        raise ProviderError(f"{NAME} refused the call: {reason}", code=details.status, raw=raw)
    return details, as_mapping(raw.get("data"))


def parse_bulk_response(raw: dict[str, Any], mobiles: Sequence[str], line: int) -> SmsResult:
    details, data = accepted_data(raw)
    ids = as_sequence(data.get("messageIds"))
    if not ids:
        raise ProviderError(
            f"{NAME} accepted the call but reported no message ids — nothing was sent",
            code=details.status,
            raw=raw,
        )
    paired = len(ids) == len(mobiles)
    messages = tuple(
        SentMessage(
            message_id=as_text(message_id) or "",
            receptor=mobiles[index] if paired else "",
            sender=str(line),
            raw={"messageId": message_id},
        )
        for index, message_id in enumerate(ids)
    )
    return SmsResult(messages=messages, cost=as_decimal(data.get("cost")), raw=raw, details=details)


def parse_pattern_response(raw: dict[str, Any], mobile: str) -> SmsResult:
    """Turn a ``send/verify`` response into a result. One recipient, so one message."""
    details, data = accepted_data(raw)
    message_id = as_text(data.get("messageId"))
    if not message_id:
        raise ProviderError(
            f"{NAME} accepted the call but reported no message id — nothing was sent",
            code=details.status,
            raw=raw,
        )
    cost = as_decimal(data.get("cost"))
    entry = SentMessage(message_id=message_id, receptor=mobile, cost=cost, raw=data)
    return SmsResult(messages=(entry,), cost=cost, raw=raw, details=details)
