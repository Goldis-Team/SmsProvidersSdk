"""One HTTP round-trip, in both flavours, shared by every provider.

The transport lives here once so that the async engine cannot quietly grow a blocking call: a
synchronous request inside a coroutine parks the entire event loop for up to the timeout, so one
slow provider stalls every other request in the process, not just the one waiting on an SMS.

**Two clients, on purpose.** ``aiohttp`` drives the async engine and has no synchronous API, so the
sync engine uses ``requests``. Both are normalised here — same arguments, same return type, same
errors — so nothing above this module can tell which one ran.

**Two encodings, on purpose.** Kavenegar takes ``application/x-www-form-urlencoded``; the providers
that came after it take JSON. Both are here rather than in the providers, so a provider module
never touches a client directly and the redaction below cannot be forgotten in one of them.

Every function raises :class:`NetworkError` for anything that stopped the round-trip from
completing, with the API key scrubbed out of the message first.
"""

import asyncio
import json
from typing import Any, cast

import aiohttp
import requests

from sms_providers_sdk.common.constants import DEFAULT_TIMEOUT
from sms_providers_sdk.common.exceptions import NetworkError
from sms_providers_sdk.common.utils import redact

JSON_HEADERS = {"Content-Type": "application/json"}


def _form_fields(payload: dict[str, Any]) -> dict[str, str]:
    """Coerce a payload to the strings a form encoder accepts.

    ``requests`` will encode ``int`` and ``bool`` happily; ``aiohttp`` raises ``TypeError`` on
    anything that is not ``str`` or ``bytes``. Normalising here is what keeps a payload that works
    on the sync engine from failing on the async one — the exact drift this module exists to stop.
    ``None`` is dropped rather than sent as the string ``"None"``, so an unset optional parameter
    is simply absent.
    """
    return {key: str(value) for key, value in payload.items() if value is not None}


def _decode(text: str, status: int, provider: str, secret: str | None) -> dict[str, Any]:
    """Decode a provider response into a dict, or say precisely what arrived instead.

    The body is parsed from text rather than through the client's own JSON helper, because these
    providers answer JSON while declaring ``text/html`` or no content type at all — ``aiohttp``
    refuses those by default.

    The HTTP status deliberately decides nothing on its own. Kavenegar mirrors its business status
    into the HTTP status — an invalid API key is a real HTTP 403, insufficient credit a real HTTP
    418 — and the body of that response is the useful part, carrying the code *and* the provider's
    own explanation. Throwing it away on status alone would replace "insufficient credit" with
    "HTTP 418". Each provider reads its own status field from the decoded body; a status that
    genuinely means the request never reached the provider's code shows up here as a body that will
    not parse.
    """
    try:
        data = json.loads(text)
    except ValueError as exc:
        clean = redact(text[:200], secret)
        raise NetworkError(
            f"{provider} answered HTTP {status} with non-JSON content: {clean!r}"
        ) from exc
    if not isinstance(data, dict):
        raise NetworkError(f"{provider} answered with {type(data).__name__}, not an object")
    # The cast is what `isinstance` cannot say: JSON object keys are strings by definition, so the
    # keys are known from here on and every provider's `.get()` off this body stays typed.
    return cast("dict[str, Any]", data)


def post_form(
    url: str,
    payload: dict[str, Any],
    *,
    provider: str,
    secret: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """POST form-encoded fields and return the decoded object. Sync engine, over ``requests``."""
    try:
        response = requests.post(
            url, data=_form_fields(payload), headers=headers or {}, timeout=timeout
        )
    except requests.Timeout as exc:
        raise NetworkError(f"{provider} did not answer within {timeout}s") from exc
    except requests.RequestException as exc:
        raise NetworkError(f"{provider} request failed: {redact(str(exc), secret)}") from exc
    return _decode(response.text, response.status_code, provider, secret)


async def apost_form(
    url: str,
    payload: dict[str, Any],
    *,
    provider: str,
    secret: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """POST form-encoded fields and return the decoded object. Async engine, over ``aiohttp``."""
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with (
            aiohttp.ClientSession(timeout=client_timeout) as session,
            session.post(url, data=_form_fields(payload), headers=headers or {}) as response,
        ):
            text = await response.text()
            status = response.status
    except asyncio.TimeoutError as exc:
        raise NetworkError(f"{provider} did not answer within {timeout}s") from exc
    except aiohttp.ClientError as exc:
        raise NetworkError(f"{provider} request failed: {redact(str(exc), secret)}") from exc
    return _decode(text, status, provider, secret)


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    provider: str,
    secret: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """POST JSON and return the decoded object. Sync engine, over ``requests``."""
    try:
        response = requests.post(
            url, json=payload, headers={**JSON_HEADERS, **(headers or {})}, timeout=timeout
        )
    except requests.Timeout as exc:
        raise NetworkError(f"{provider} did not answer within {timeout}s") from exc
    except requests.RequestException as exc:
        raise NetworkError(f"{provider} request failed: {redact(str(exc), secret)}") from exc
    return _decode(response.text, response.status_code, provider, secret)


async def apost_json(
    url: str,
    payload: dict[str, Any],
    *,
    provider: str,
    secret: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """POST JSON and return the decoded object. Async engine, over ``aiohttp``."""
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with (
            aiohttp.ClientSession(timeout=client_timeout) as session,
            session.post(
                url, json=payload, headers={**JSON_HEADERS, **(headers or {})}
            ) as response,
        ):
            text = await response.text()
            status = response.status
    except asyncio.TimeoutError as exc:
        raise NetworkError(f"{provider} did not answer within {timeout}s") from exc
    except aiohttp.ClientError as exc:
        raise NetworkError(f"{provider} request failed: {redact(str(exc), secret)}") from exc
    return _decode(text, status, provider, secret)
