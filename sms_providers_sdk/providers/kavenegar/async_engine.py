"""Kavenegar, async engine."""

from typing import Any

from sms_providers_sdk.common.constants import DEFAULT_TIMEOUT
from sms_providers_sdk.common.data import (
    BulkSmsMessage,
    PatternMessage,
    SmsMessage,
    SmsResult,
)
from sms_providers_sdk.common.http import apost_form
from sms_providers_sdk.common.utils import check_credential
from sms_providers_sdk.providers.kavenegar.constants import LOOKUP, NAME, SEND
from sms_providers_sdk.providers.kavenegar.data import KavenegarConfig
from sms_providers_sdk.providers.kavenegar.helpers import (
    build_bulk_payload,
    build_pattern_payload,
    build_send_payload,
    endpoint,
    parse_response,
)


class KavenegarAsync:
    name = NAME

    def __init__(
        self,
        api_key: str,
        *,
        sender: str = "",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.config = KavenegarConfig(
            api_key=check_credential(api_key, provider=NAME, field="api_key"),
            sender=sender.strip(),
        )
        self.timeout = timeout

    async def _post(self, scope: str, method: str, payload: dict[str, Any]) -> SmsResult:
        raw = await apost_form(
            endpoint(self.config, scope, method),
            payload,
            provider=self.name,
            secret=self.config.api_key,
            timeout=self.timeout,
        )
        return parse_response(raw)

    async def send(self, message: SmsMessage) -> SmsResult:
        """One message to one recipient."""
        return await self._post(*SEND, build_send_payload(self.config, message))

    async def send_bulk(self, message: BulkSmsMessage) -> SmsResult:
        """The same message to up to 200 recipients, in one call."""
        return await self._post(*SEND, build_bulk_payload(self.config, message))

    async def send_pattern(self, message: PatternMessage) -> SmsResult:
        """A message built from a template registered in the Kavenegar panel."""
        return await self._post(*LOOKUP, build_pattern_payload(self.config, message))
