from dataclasses import dataclass, field

from sms_providers_sdk.common.data import ProviderDetails


@dataclass(frozen=True)
class MelipayamakConfig:
    api_key: str = field(repr=False)

    sender: str = ""


@dataclass(frozen=True)
class MelipayamakDetails(ProviderDetails):
    status_message: str | None = None

    rec_ids: tuple[str, ...] = ()
