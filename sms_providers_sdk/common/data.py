from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


def _empty() -> dict[str, Any]:
    return {}


@dataclass(frozen=True)
class ProviderDetails:
    pass


@dataclass(frozen=True)
class SmsMessage:
    """One message to one recipient."""

    receptor: str

    text: str
    """The message body. Sent as-is; no provider here needs it pre-encoded."""

    sender: str = ""
    """The line to send from. Falls back to the provider's configured default line when empty."""

    send_at: int | None = None
    """Unix timestamp to schedule the message for, or ``None`` to send now."""

    local_id: str = ""

    extra: Mapping[str, Any] = field(default_factory=_empty)
    """Provider-specific parameters, merged into the payload verbatim."""


@dataclass(frozen=True)
class BulkSmsMessage:
    receptors: Sequence[str]
    """The recipients' numbers. Each is normalised the same way as :attr:`SmsMessage.receptor`."""

    text: str
    """The message body, the same for every recipient."""

    sender: str = ""
    """The line to send from. Falls back to the provider's configured default line when empty."""

    send_at: int | None = None
    """Unix timestamp to schedule the batch for, or ``None`` to send now."""

    local_ids: Sequence[str] = ()

    extra: Mapping[str, Any] = field(default_factory=_empty)
    """Provider-specific parameters, merged into the payload verbatim."""


@dataclass(frozen=True)
class PatternMessage:
    receptor: str
    """The recipient's number, normalised like :attr:`SmsMessage.receptor`."""

    pattern: str
    """The template's name or id at the provider — Kavenegar's ``template``."""

    tokens: Sequence[str] | Mapping[str, str] = ()

    sender: str = ""
    """The line to send from, where the provider allows overriding the template's own line."""

    extra: Mapping[str, Any] = field(default_factory=_empty)
    """Provider-specific parameters, merged into the payload verbatim."""


@dataclass(frozen=True)
class SentMessage:
    message_id: str
    """The provider's id for this message. The handle for every later question about it."""

    receptor: str

    status: int | None = None
    """The provider's status code for this message at send time."""

    status_text: str | None = None
    """What that code means, in the provider's own words where it sends them."""

    sender: str | None = None

    text: str | None = None

    cost: Decimal | None = None

    sent_at: int | None = None
    """Unix timestamp the provider stamped the message with."""

    local_id: str | None = None
    """Your own id, echoed back where the provider supports it."""

    raw: dict[str, Any] = field(default_factory=_empty)
    """This entry from the provider's response, untouched."""


@dataclass(frozen=True)
class SmsResult:
    messages: tuple[SentMessage, ...] = ()
    """One entry per recipient the provider accepted, in the order it reported them."""

    cost: Decimal | None = None

    raw: dict[str, Any] = field(default_factory=_empty)
    """The provider's decoded response, untouched, for logging and support tickets."""

    details: ProviderDetails | None = None
    """Everything this particular provider reported at the call level, as its own typed record."""

    def __bool__(self) -> bool:
        """``True`` when at least one message was accepted."""
        return bool(self.messages)

    def __len__(self) -> int:
        return len(self.messages)

    def __iter__(self) -> Iterator[SentMessage]:
        return iter(self.messages)

    @property
    def first(self) -> SentMessage | None:
        """The single message, for the single-recipient calls where there is only ever one."""
        return self.messages[0] if self.messages else None

    @property
    def message_id(self) -> str | None:
        """The first message's id — the one you store after a :meth:`send` or pattern send."""
        return self.messages[0].message_id if self.messages else None

    @property
    def message_ids(self) -> tuple[str, ...]:
        """Every id, for a bulk send."""
        return tuple(entry.message_id for entry in self.messages)

    @property
    def receptors(self) -> tuple[str, ...]:
        """Every recipient the provider accepted, in the order it reported them."""
        return tuple(entry.receptor for entry in self.messages)
