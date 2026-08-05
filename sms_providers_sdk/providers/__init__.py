from typing import Any

from sms_providers_sdk.common.exceptions import ConfigurationError
from sms_providers_sdk.common.interfaces import IAsyncSmsProvider, ISyncSmsProvider
from sms_providers_sdk.providers.kavenegar import KavenegarAsync as KavenegarAsync
from sms_providers_sdk.providers.kavenegar import KavenegarConfig as KavenegarConfig
from sms_providers_sdk.providers.kavenegar import KavenegarDetails as KavenegarDetails
from sms_providers_sdk.providers.kavenegar import KavenegarSync as KavenegarSync
from sms_providers_sdk.providers.melipayamak import MelipayamakAsync as MelipayamakAsync
from sms_providers_sdk.providers.melipayamak import MelipayamakConfig as MelipayamakConfig
from sms_providers_sdk.providers.melipayamak import MelipayamakDetails as MelipayamakDetails
from sms_providers_sdk.providers.melipayamak import MelipayamakSync as MelipayamakSync
from sms_providers_sdk.providers.smsir import SmsIrAsync as SmsIrAsync
from sms_providers_sdk.providers.smsir import SmsIrConfig as SmsIrConfig
from sms_providers_sdk.providers.smsir import SmsIrDetails as SmsIrDetails
from sms_providers_sdk.providers.smsir import SmsIrSync as SmsIrSync

SYNC_PROVIDERS: dict[str, type[ISyncSmsProvider]] = {
    "kavenegar": KavenegarSync,
    "melipayamak": MelipayamakSync,
    "smsir": SmsIrSync,
}

ASYNC_PROVIDERS: dict[str, type[IAsyncSmsProvider]] = {
    "kavenegar": KavenegarAsync,
    "melipayamak": MelipayamakAsync,
    "smsir": SmsIrAsync,
}


def available() -> tuple[str, ...]:
    """Every provider name, sorted. The same names work in both engines."""
    return tuple(sorted(SYNC_PROVIDERS))


def get_sync_provider(name: str, **credentials: Any) -> ISyncSmsProvider:
    """Build a sync provider by name, e.g. ``get_sync_provider("kavenegar", api_key="…")``."""
    try:
        provider_cls = SYNC_PROVIDERS[name]
    except KeyError:
        raise ConfigurationError(
            f"unknown provider {name!r} — available: {', '.join(available())}"
        ) from None
    return provider_cls(**credentials)


def get_async_provider(name: str, **credentials: Any) -> IAsyncSmsProvider:
    """Build an async provider by name, e.g. ``get_async_provider("kavenegar", api_key="…")``."""
    try:
        provider_cls = ASYNC_PROVIDERS[name]
    except KeyError:
        raise ConfigurationError(
            f"unknown provider {name!r} — available: {', '.join(available())}"
        ) from None
    return provider_cls(**credentials)
