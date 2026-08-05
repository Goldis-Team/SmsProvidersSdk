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
    return {key: str(value) for key, value in payload.items() if value is not None}


def _decode(text: str, status: int, provider: str, secret: str | None) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except ValueError as exc:
        clean = redact(text[:200], secret)
        raise NetworkError(
            f"{provider} answered HTTP {status} with non-JSON content: {clean!r}"
        ) from exc
    if not isinstance(data, dict):
        raise NetworkError(f"{provider} answered with {type(data).__name__}, not an object")
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
