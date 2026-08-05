"""Melipayamak, async engine."""

from typing import Any

from sms_providers_sdk.common.constants import DEFAULT_TIMEOUT
from sms_providers_sdk.common.data import (
    BulkSmsMessage,
    PatternMessage,
    SmsMessage,
    SmsResult,
)
from sms_providers_sdk.common.http import apost_json
from sms_providers_sdk.common.utils import check_credential
from sms_providers_sdk.providers.melipayamak.constants import (
    ADVANCED_PATH,
    NAME,
    SHARED_PATH,
    SIMPLE_PATH,
)
from sms_providers_sdk.providers.melipayamak.data import MelipayamakConfig
from sms_providers_sdk.providers.melipayamak.helpers import (
    build_advanced_payload,
    build_shared_payload,
    build_simple_payload,
    endpoint,
    parse_advanced_response,
    parse_single_response,
)


class MelipayamakAsync:
    """Melipayamak over the async engine. Satisfies
    :class:`~sms_providers_sdk.common.interfaces.IAsyncSmsProvider`."""

    name = NAME

    def __init__(
        self,
        api_key: str,
        *,
        sender: str = "",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.config = MelipayamakConfig(
            api_key=check_credential(api_key, provider=NAME, field="api_key"),
            sender=sender.strip(),
        )
        self.timeout = timeout

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """One round-trip. ``secret`` is the API key, scrubbed from any error text on the way out —
        it is a path segment of the URL, which both HTTP clients put in their exceptions."""
        return await apost_json(
            endpoint(self.config, path),
            payload,
            provider=self.name,
            secret=self.config.api_key,
            timeout=self.timeout,
        )

    async def send(self, message: SmsMessage) -> SmsResult:
        """One message to one recipient."""
        payload = build_simple_payload(self.config, message)
        raw = await self._post(SIMPLE_PATH, payload)
        return parse_single_response(raw, payload["to"])

    async def send_bulk(self, message: BulkSmsMessage) -> SmsResult:
        """The same message to many recipients, in one call."""
        payload = build_advanced_payload(self.config, message)
        raw = await self._post(ADVANCED_PATH, payload)
        return parse_advanced_response(raw, payload["to"], payload["from"])

    async def send_pattern(self, message: PatternMessage) -> SmsResult:
        """A message built from a template registered in the Melipayamak console."""
        payload = build_shared_payload(message)
        raw = await self._post(SHARED_PATH, payload)
        return parse_single_response(raw, payload["to"])
