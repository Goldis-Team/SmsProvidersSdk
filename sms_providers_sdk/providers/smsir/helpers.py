"""SMS.ir — payload building and response reading.

Everything that decides what SMS.ir was asked and what it answered lives here, so the sync and
async engines are thin shells over the same logic and cannot drift apart.
"""

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
    """The sending line for this message, as the integer SMS.ir declares it to be.

    Required, and with no server-side default to fall back on: SMS.ir answers a missing or unknown
    line with status 101, which reads identically whether the line was omitted, mistyped, or simply
    not owned by the account. Saying which of those it is only works here.
    """
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
    """``send/bulk`` with one recipient.

    SMS.ir has no dedicated single-send endpoint for free-form text, so this is the same call with
    a one-element list. The response shape is the same too, which is why both go through
    :func:`parse_bulk_response`.
    """
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
    """``send/bulk`` — one text, one line, up to 100 numbers.

    ``local_ids`` has nowhere to go: SMS.ir has no client-supplied message reference, only the
    ``packId`` it assigns. Refusing them is better than accepting them into a void, since the whole
    point of a local id is that it comes back.
    """
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
    """The template's values as SMS.ir's ``[{"name": …, "value": …}]``.

    A mapping only. SMS.ir placeholders are ``#NAME#`` and the API matches on the name, so a
    positional sequence has nothing to map onto — there is no documented ordering to fall back on,
    and inventing one would put the right value in the wrong slot of a message that has already
    been sent. Kavenegar's numbered tokens are the exception here, not the rule.
    """
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
    """``send/verify`` — one recipient, one template, its named parameters.

    Like Kavenegar's lookup, this has no line parameter: the line belongs to the template, fixed
    when it was approved. A ``sender`` would be dropped without trace, so it is refused instead.
    """
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
    """The ``data`` object, once the call is known to have been accepted.

    Raises with SMS.ir's own code on anything else — bad key, no credit, unknown template, a
    recipient on the platform blacklist — so a caller can branch on ``exc.code``.
    """
    details = read_details(raw)
    if details.status != SUCCESS_STATUS:
        reason = details.status_description or details.status_message or f"status {details.status}"
        raise ProviderError(f"{NAME} refused the call: {reason}", code=details.status, raw=raw)
    return details, as_mapping(raw.get("data"))


def parse_bulk_response(raw: dict[str, Any], mobiles: Sequence[str], line: int) -> SmsResult:
    """Turn a bulk-send response into a result, or raise with what SMS.ir actually said.

    SMS.ir echoes no recipients: ``data.messageIds`` is a flat list, documented as being in the
    order the numbers were submitted. So the numbers are paired back by position — but only when
    the counts match. If they do not, the pairing is unknowable and the recipients are left blank
    rather than guessed, because an id attributed to the wrong number is worse than one attributed
    to nobody.
    """
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
    # The cost is reported once for the batch, not per message, so it belongs on the result and
    # `SentMessage.cost` stays None — see the note on `SmsResult.cost`.
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
    # One message, so the call's cost and the message's cost are the same number.
    entry = SentMessage(message_id=message_id, receptor=mobile, cost=cost, raw=data)
    return SmsResult(messages=(entry,), cost=cost, raw=raw, details=details)
