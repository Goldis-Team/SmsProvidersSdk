"""Value objects shared by every provider, in both engines.

Three things go in — :class:`SmsMessage`, :class:`BulkSmsMessage`, :class:`PatternMessage` — and
one thing comes back, :class:`SmsResult`, holding a :class:`SentMessage` per recipient the provider
accepted.

Every input carries an ``extra`` mapping. Providers differ in the long tail — Kavenegar's ``hide``
and ``type``, another provider's campaign id — and forcing those into the shared shape would make
it the union of every provider rather than the part that is actually common. ``extra`` is merged
into the outgoing payload as-is, so the escape hatch does not require dropping out of the SDK.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


def _empty() -> dict[str, Any]:
    """The default for every ``extra`` and ``raw`` field.

    ``default_factory=dict`` would do the same at runtime, but ``dict`` is generic and a type
    checker cannot infer its parameters from the field's annotation — so every one of those fields
    reads as ``dict[Unknown, Unknown]`` under strict mode, and so does anything pulled out of it.
    Naming the factory pins the type once.
    """
    return {}


@dataclass(frozen=True)
class ProviderDetails:
    """Base for the per-provider detail records.

    Each provider defines its own subclass in its ``data.py`` carrying everything *that* provider
    reports at the call level — Kavenegar's ``return`` object and what its status code means. It
    arrives on :attr:`SmsResult.details`, typed, so reading provider-specific data does not mean
    digging through ``raw``.
    """


@dataclass(frozen=True)
class SmsMessage:
    """One message to one recipient."""

    receptor: str
    """The recipient's number. Normalised before sending: Persian and Arabic-Indic digits are
    folded to ASCII, spaces and dashes dropped, and ``+98``/``0098``/``98`` rewritten to a leading
    ``0`` — see :func:`~sms_providers_sdk.common.utils.normalize_number`."""

    text: str
    """The message body. Sent as-is; no provider here needs it pre-encoded."""

    sender: str = ""
    """The line to send from. Falls back to the provider's configured default line when empty."""

    send_at: int | None = None
    """Unix timestamp to schedule the message for, or ``None`` to send now."""

    local_id: str = ""
    """Your own id for this message, echoed back by providers that support it.

    Worth setting: it is what makes a retried send idempotent on the provider's side, and what lets
    you match a delivery report to your own record without storing the provider's id first.
    """

    extra: Mapping[str, Any] = field(default_factory=_empty)
    """Provider-specific parameters, merged into the payload verbatim."""


@dataclass(frozen=True)
class BulkSmsMessage:
    """The same message to many recipients, in one call.

    One text, one sender, many numbers — which is what "group send" means at every provider here.
    Sending *different* texts to different numbers is not this; issue separate
    :class:`SmsMessage` calls for that.

    Providers cap how many recipients one call takes (Kavenegar: 200). The cap is checked before
    the request goes out, because a provider that rejects the batch rejects **all** of it.
    """

    receptors: Sequence[str]
    """The recipients' numbers. Each is normalised the same way as :attr:`SmsMessage.receptor`."""

    text: str
    """The message body, the same for every recipient."""

    sender: str = ""
    """The line to send from. Falls back to the provider's configured default line when empty."""

    send_at: int | None = None
    """Unix timestamp to schedule the batch for, or ``None`` to send now."""

    local_ids: Sequence[str] = ()
    """Your own ids, one per recipient in the same order. Either empty, or exactly as long as
    :attr:`receptors` — a partial list would silently pair ids with the wrong numbers."""

    extra: Mapping[str, Any] = field(default_factory=_empty)
    """Provider-specific parameters, merged into the payload verbatim."""


@dataclass(frozen=True)
class PatternMessage:
    """A message built from a template registered with the provider.

    This is the route for one-time codes and transactional notices. It is not a convenience over
    :class:`SmsMessage`: templates are pre-approved, so they are delivered on service lines that
    reach numbers which have opted out of advertising, they are billed differently, and they are
    generally the only way to send at all outside business hours.
    """

    receptor: str
    """The recipient's number, normalised like :attr:`SmsMessage.receptor`."""

    pattern: str
    """The template's name or id at the provider — Kavenegar's ``template``."""

    tokens: Sequence[str] | Mapping[str, str] = ()
    """The values substituted into the template.

    A sequence fills the template's placeholders in order. A mapping names them, for providers
    whose templates use named parameters. Each provider documents which placeholder names it maps
    a sequence onto — Kavenegar's are ``token``, ``token2`` … ``token20``.
    """

    sender: str = ""
    """The line to send from, where the provider allows overriding the template's own line."""

    extra: Mapping[str, Any] = field(default_factory=_empty)
    """Provider-specific parameters, merged into the payload verbatim."""


@dataclass(frozen=True)
class SentMessage:
    """One recipient's message, as the provider recorded it.

    ``status`` here is the state at the moment of the call — queued, scheduled, sent to the
    operator. It is not a delivery confirmation; delivery is reported minutes later, out of band.
    Store :attr:`message_id` if you intend to ask about it.
    """

    message_id: str
    """The provider's id for this message. The handle for every later question about it."""

    receptor: str
    """The recipient, as the provider echoed it back — which may differ in format from what was
    sent, so this is the value to log."""

    status: int | None = None
    """The provider's status code for this message at send time."""

    status_text: str | None = None
    """What that code means, in the provider's own words where it sends them."""

    sender: str | None = None
    """The line the provider actually sent from — useful when the account has a default line
    configured server-side and none was passed."""

    text: str | None = None
    """The body as the provider stored it. For a pattern send, this is the *rendered* text, which
    is the only place the substituted template becomes visible."""

    cost: Decimal | None = None
    """What this message cost, in the provider's own accounting unit — Rial for Kavenegar, a
    credit count for SMS.ir.

    ``Decimal`` because those units are not all integers: SMS.ir prices a message at ``1.0``
    credits and a long one at a fraction more, and ``float`` is the wrong type for anything that
    gets summed and reconciled against an invoice. It compares equal to the matching ``int``, so
    ``entry.cost == 120`` reads the same as it would have.

    ``None`` where the provider reports cost only for the call as a whole — see
    :attr:`SmsResult.cost`.
    """

    sent_at: int | None = None
    """Unix timestamp the provider stamped the message with."""

    local_id: str | None = None
    """Your own id, echoed back where the provider supports it."""

    raw: dict[str, Any] = field(default_factory=_empty)
    """This entry from the provider's response, untouched."""


@dataclass(frozen=True)
class SmsResult:
    """What the provider accepted.

    There is no ``success`` flag, on purpose. A send that failed raised — see
    :mod:`sms_providers_sdk.common.exceptions` — so a result in your hands is already the
    successful case, and a boolean that is always ``True`` is a check people write and never
    exercise. What is worth inspecting is :attr:`messages`: how many recipients were accepted, at
    what cost, under which ids.
    """

    messages: tuple[SentMessage, ...] = ()
    """One entry per recipient the provider accepted, in the order it reported them."""

    cost: Decimal | None = None
    """What the whole call cost, or ``None`` where the provider reported nothing.

    A field rather than a sum over :attr:`messages`, because the providers disagree about where
    the number lives: Kavenegar prices each message and this is their total, SMS.ir prices the
    batch and says nothing per recipient. Deriving it would have meant inventing a per-message
    figure for SMS.ir by dividing, which is a guess about billing — so each provider fills in
    whichever one it actually got told.
    """

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
