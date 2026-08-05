"""The two engine interfaces.

Both protocols carry the same three methods with the same arguments and the same return types; the
only difference is the ``async``. Porting a call site from one engine to the other is adding or
removing ``await``, never a rewrite — which is the whole point of shipping both.

These are :class:`typing.Protocol`, so providers satisfy them structurally. No provider inherits
from anything here, and your own provider does not have to either.
"""

from typing import Protocol, runtime_checkable

from sms_providers_sdk.common.data import (
    BulkSmsMessage,
    PatternMessage,
    SmsMessage,
    SmsResult,
)


@runtime_checkable
class IAsyncSmsProvider(Protocol):
    """The async engine: for FastAPI, aiohttp, and anything else on asyncio."""

    name: str

    async def send(self, message: SmsMessage) -> SmsResult: ...

    async def send_bulk(self, message: BulkSmsMessage) -> SmsResult: ...

    async def send_pattern(self, message: PatternMessage) -> SmsResult: ...


@runtime_checkable
class ISyncSmsProvider(Protocol):
    """The sync engine: for scripts, Django, and Celery workers."""

    name: str

    def send(self, message: SmsMessage) -> SmsResult: ...

    def send_bulk(self, message: BulkSmsMessage) -> SmsResult: ...

    def send_pattern(self, message: PatternMessage) -> SmsResult: ...
