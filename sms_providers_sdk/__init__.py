"""A unified SDK for Iranian SMS providers, in a sync and an async flavour.

Every provider ships ``<Name>Sync`` and ``<Name>Async`` with the same three methods —
:meth:`send`, :meth:`send_bulk` and :meth:`send_pattern` — taking and returning the same types.
Moving between engines is adding or removing ``await``, never a rewrite.

    from sms_providers_sdk import KavenegarSync, SmsMessage

    sms = KavenegarSync(api_key="…")
    result = sms.send(SmsMessage(receptor="09121234567", text="سلام"))
    print(result.message_id)

A send that did not happen **raises** — :class:`ProviderError` when the provider refused,
:class:`NetworkError` when it could not be reached, :class:`ConfigurationError` when the message
could not be built. What comes back is :class:`SmsResult`, a description of what the provider
accepted, with one :class:`SentMessage` per recipient.

Each provider package is laid out the same way: ``constants.py`` (endpoints and the fixed values
its protocol defines), ``data.py`` (credentials and the provider's own result records — dataclasses
only), ``helpers.py`` (the pure functions that build payloads and read responses), and
``sync_engine.py`` / ``async_engine.py``.
"""

from sms_providers_sdk.common.data import BulkSmsMessage as BulkSmsMessage
from sms_providers_sdk.common.data import PatternMessage as PatternMessage
from sms_providers_sdk.common.data import ProviderDetails as ProviderDetails
from sms_providers_sdk.common.data import SentMessage as SentMessage
from sms_providers_sdk.common.data import SmsMessage as SmsMessage
from sms_providers_sdk.common.data import SmsResult as SmsResult
from sms_providers_sdk.common.exceptions import ConfigurationError as ConfigurationError
from sms_providers_sdk.common.exceptions import NetworkError as NetworkError
from sms_providers_sdk.common.exceptions import ProviderError as ProviderError
from sms_providers_sdk.common.exceptions import SmsError as SmsError
from sms_providers_sdk.common.exceptions import UnsupportedOperation as UnsupportedOperation
from sms_providers_sdk.common.interfaces import IAsyncSmsProvider as IAsyncSmsProvider
from sms_providers_sdk.common.interfaces import ISyncSmsProvider as ISyncSmsProvider
from sms_providers_sdk.providers import KavenegarAsync as KavenegarAsync
from sms_providers_sdk.providers import KavenegarConfig as KavenegarConfig
from sms_providers_sdk.providers import KavenegarDetails as KavenegarDetails
from sms_providers_sdk.providers import KavenegarSync as KavenegarSync
from sms_providers_sdk.providers import MelipayamakAsync as MelipayamakAsync
from sms_providers_sdk.providers import MelipayamakConfig as MelipayamakConfig
from sms_providers_sdk.providers import MelipayamakDetails as MelipayamakDetails
from sms_providers_sdk.providers import MelipayamakSync as MelipayamakSync
from sms_providers_sdk.providers import SmsIrAsync as SmsIrAsync
from sms_providers_sdk.providers import SmsIrConfig as SmsIrConfig
from sms_providers_sdk.providers import SmsIrDetails as SmsIrDetails
from sms_providers_sdk.providers import SmsIrSync as SmsIrSync
from sms_providers_sdk.providers import available as available
from sms_providers_sdk.providers import get_async_provider as get_async_provider
from sms_providers_sdk.providers import get_sync_provider as get_sync_provider

__version__ = "0.1.0"
