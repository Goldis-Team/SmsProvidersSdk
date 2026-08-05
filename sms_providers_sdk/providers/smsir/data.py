from dataclasses import dataclass, field

from sms_providers_sdk.common.data import ProviderDetails


@dataclass(frozen=True)
class SmsIrConfig:
    api_key: str = field(repr=False)

    line_number: str = ""


@dataclass(frozen=True)
class SmsIrDetails(ProviderDetails):
    status: int | None = None
    """SMS.ir's ``status``. ``1`` is the only value that means accepted."""

    status_message: str | None = None
    """SMS.ir's own text for that status, in Persian, exactly as sent."""

    status_description: str | None = None

    pack_id: str | None = None
