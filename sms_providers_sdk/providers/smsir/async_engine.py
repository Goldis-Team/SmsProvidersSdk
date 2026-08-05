"""SMS.ir, async engine."""

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
from sms_providers_sdk.providers.smsir.constants import BULK_PATH, NAME, VERIFY_PATH
from sms_providers_sdk.providers.smsir.data import SmsIrConfig
from sms_providers_sdk.providers.smsir.helpers import (
    auth_headers,
    build_bulk_payload,
    build_pattern_payload,
    build_single_payload,
    endpoint,
    parse_bulk_response,
    parse_pattern_response,
)


class SmsIrAsync:
    name = NAME

    def __init__(
        self,
        api_key: str,
        *,
        line_number: str = "",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.config = SmsIrConfig(
            api_key=check_credential(api_key, provider=NAME, field="api_key"),
            line_number=line_number.strip(),
        )
        self.timeout = timeout

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await apost_json(
            endpoint(path),
            payload,
            provider=self.name,
            secret=self.config.api_key,
            headers=auth_headers(self.config),
            timeout=self.timeout,
        )

    async def send(self, message: SmsMessage) -> SmsResult:
        """One message to one recipient, over ``send/bulk`` with a one-element list."""
        payload = build_single_payload(self.config, message)
        raw = await self._post(BULK_PATH, payload)
        return parse_bulk_response(raw, payload["mobiles"], payload["lineNumber"])

    async def send_bulk(self, message: BulkSmsMessage) -> SmsResult:
        """The same message to up to 100 recipients, in one call."""
        payload = build_bulk_payload(self.config, message)
        raw = await self._post(BULK_PATH, payload)
        return parse_bulk_response(raw, payload["mobiles"], payload["lineNumber"])

    async def send_pattern(self, message: PatternMessage) -> SmsResult:
        """A message built from a template registered in the SMS.ir panel."""
        payload = build_pattern_payload(self.config, message)
        raw = await self._post(VERIFY_PATH, payload)
        return parse_pattern_response(raw, payload["mobile"])
