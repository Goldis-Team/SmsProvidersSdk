from dataclasses import dataclass, field

from sms_providers_sdk.common.data import ProviderDetails


@dataclass(frozen=True)
class KavenegarConfig:
    api_key: str = field(repr=False)

    sender: str = ""


@dataclass(frozen=True)
class KavenegarDetails(ProviderDetails):
    return_status: int | None = None
    """Kavenegar's ``return.status``. ``200`` is the only value that means accepted."""

    return_message: str | None = None
    """Kavenegar's own text for that status, in Persian, exactly as sent."""

    status_description: str | None = None
