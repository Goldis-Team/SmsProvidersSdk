"""How to use sms-providers-sdk.

Nothing here runs without credentials — an SMS provider has no public sandbox, and every send costs
money. Set ``KAVENEGAR_API_KEY`` and run ``python main.py`` to send one real message to the number
in ``RECEPTOR``; without it, this file is example code to copy.

The whole SDK is three calls:

    sms.send(SmsMessage(...))               # one message, one recipient
    sms.send_bulk(BulkSmsMessage(...))      # one message, many recipients
    sms.send_pattern(PatternMessage(...))   # a template registered at the provider

Every provider ships two classes with those same three methods — ``<Name>Sync`` and
``<Name>Async``. Moving between engines is adding or removing ``await``, never a rewrite.

A send that did not happen **raises**. What comes back is a description of what was accepted.
"""

import asyncio
import os

from sms_providers_sdk import (
    BulkSmsMessage,
    ConfigurationError,
    KavenegarAsync,
    KavenegarSync,
    MelipayamakSync,
    NetworkError,
    PatternMessage,
    ProviderError,
    SmsError,
    SmsIrDetails,
    SmsIrSync,
    SmsMessage,
    SmsResult,
    available,
    get_async_provider,
    get_sync_provider,
)

RECEPTOR = "09121234567"


# ---------------------------------------------------------------------------------------------
# 1. The sync engine — scripts, Django, Celery workers
# ---------------------------------------------------------------------------------------------


def send_one(api_key: str) -> str:
    """One message to one recipient. Returns the id to store against your own record.

    ``sender`` is left off: most accounts have a default line configured in the panel, and
    Kavenegar uses it when none is passed. Set ``KavenegarSync(api_key, sender="10004346")`` to
    pin every message from this instance to one line.
    """
    sms = KavenegarSync(api_key)
    result = sms.send(SmsMessage(receptor=RECEPTOR, text="سفارش شما ثبت شد."))

    entry = result.first
    assert entry is not None  # a returned result always has at least one message
    print(f"sent {entry.message_id} from {entry.sender} for {entry.cost}")
    return entry.message_id


def send_to_a_group(api_key: str, numbers: list[str]) -> SmsResult:
    """The same message to many recipients, in one call.

    Kavenegar takes 200 per call and rejects an oversized batch **whole**, so the SDK refuses it
    up front rather than letting the whole send disappear. Chunk longer lists yourself.

    ``hide=1`` is a Kavenegar-specific parameter and goes through ``extra``: it keeps recipients
    from seeing each other's numbers, which matters the moment the group is customers rather than
    colleagues.
    """
    result = KavenegarSync(api_key).send_bulk(
        BulkSmsMessage(
            receptors=numbers,
            text="فروشگاه فردا تعطیل است.",
            extra={"hide": 1},
        )
    )
    print(f"{len(result)} accepted, total cost {result.cost}")
    return result


def send_a_one_time_code(api_key: str, code: str) -> str:
    """A pattern (template) send — the route for one-time codes and transactional notices.

    Templates are pre-approved in the Kavenegar panel, so they reach numbers that have opted out
    of advertising, they are billed differently, and they are generally the only thing that goes
    out at night. The template's ``%token`` placeholders are filled in order.

    Two things Kavenegar will not tell you clearly, and the SDK refuses before sending:

    * **No spaces** in any token except ``token10`` and ``token20``. A name with a space in it is
      the usual cause of a template send that "just fails". Pass it as ``{"token10": "علی رضایی"}``,
      or replace the space with a ZWNJ.
    * **No sender.** The line belongs to the template, set when it was approved.
    """
    result = KavenegarSync(api_key).send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="verify", tokens=[code])
    )
    entry = result.first
    assert entry is not None
    print(f"code sent as {entry.message_id}; rendered text: {entry.text}")
    return entry.message_id


def scheduled_and_traceable(api_key: str, when: int) -> SmsResult:
    """A message scheduled for later, tagged with your own id.

    ``local_id`` is worth setting on anything that matters: it is what makes a retried send
    idempotent at the provider, and what lets a delivery report find your record without having
    stored the provider's id first.
    """
    return KavenegarSync(api_key).send(
        SmsMessage(
            receptor=RECEPTOR,
            text="یادآوری نوبت فردا ساعت ۱۰.",
            send_at=when,
            local_id="appointment-8842",
        )
    )


# ---------------------------------------------------------------------------------------------
# 2. The async engine — FastAPI, aiohttp, anything on asyncio
# ---------------------------------------------------------------------------------------------


async def send_one_async(api_key: str) -> str:
    """The same call, awaited. Same arguments, same result type."""
    sms = KavenegarAsync(api_key)
    result = await sms.send(SmsMessage(receptor=RECEPTOR, text="سفارش شما ثبت شد."))
    return result.message_id or ""


async def send_several_concurrently(api_key: str, texts: list[str]) -> list[SmsResult]:
    """Different texts to the same recipient, at once.

    ``send_bulk`` is one text to many numbers. When the texts differ there is no single call for
    it, so the async engine is what keeps it from being N round-trips in series.
    """
    sms = KavenegarAsync(api_key)
    return await asyncio.gather(
        *(sms.send(SmsMessage(receptor=RECEPTOR, text=text)) for text in texts)
    )


# ---------------------------------------------------------------------------------------------
# 3. Handling failures
# ---------------------------------------------------------------------------------------------


def send_carefully(api_key: str, text: str) -> str | None:
    """The three ways a send fails, and what each one means for what you do next.

    ``ProviderError`` carries Kavenegar's own numeric code on ``.code``, which is what you branch
    on: 418 (no credit) is for an operator, 424 (unknown template) is a deploy problem, 451 (rate
    limited) is worth retrying.
    """
    try:
        result = KavenegarSync(api_key).send(SmsMessage(receptor=RECEPTOR, text=text))
    except ConfigurationError as exc:
        # The message could not be built. Nothing was sent, and retrying changes nothing.
        print(f"bad input: {exc}")
        return None
    except ProviderError as exc:
        # Kavenegar was reached and refused. Nothing was sent.
        print(f"refused with code {exc.code}: {exc}")
        return None
    except NetworkError as exc:
        # Unreachable or timed out. This is the ambiguous one: the message may or may not have
        # gone out. Retry with the same `local_id` so the provider deduplicates it.
        print(f"unreachable: {exc}")
        return None
    return result.message_id


def status_of_each_recipient(result: SmsResult) -> None:
    """What a bulk result actually tells you.

    The status here is the state at send time — queued, or scheduled for later. It is **not** a
    delivery confirmation: delivery is reported minutes afterwards, through a status call or a
    webhook, against the ids below.
    """
    for entry in result:
        print(f"{entry.receptor}: {entry.status_text} (id {entry.message_id})")


# ---------------------------------------------------------------------------------------------
# 4. Choosing a provider at runtime
# ---------------------------------------------------------------------------------------------


def from_configuration(name: str, api_key: str) -> str | None:
    """Build a provider by name, for when it comes out of settings rather than an import.

    The registry holds classes, not instances — one instance carries one account's credentials, so
    build one per account rather than caching a provider globally.
    """
    print(f"available: {', '.join(available())}")
    sms = get_sync_provider(name, api_key=api_key)
    return sms.send(SmsMessage(receptor=RECEPTOR, text="سلام")).message_id


async def from_configuration_async(name: str, api_key: str) -> str | None:
    sms = get_async_provider(name, api_key=api_key)
    result = await sms.send(SmsMessage(receptor=RECEPTOR, text="سلام"))
    return result.message_id


# ---------------------------------------------------------------------------------------------
# 5. The same three calls on SMS.ir
# ---------------------------------------------------------------------------------------------


def the_same_code_on_smsir(api_key: str) -> None:
    """Identical call sites, a different provider behind them.

    Four differences are worth knowing, and the SDK enforces each one before the request goes out
    rather than letting it come back as a numeric code:

    * **The line number is required.** SMS.ir has no account-level default to fall back on, so it
      is either on the provider or on the message.
    * **100 recipients per batch**, not Kavenegar's 200.
    * **Templates are numeric ids**, not names — ``pattern="100000"``, not ``pattern="verify"``.
    * **Template parameters are named.** SMS.ir placeholders are ``#NAME#`` and the API matches on
      the name, so a positional list has nothing to map onto and is refused.
    """
    sms = SmsIrSync(api_key, line_number="30007487")

    sms.send(SmsMessage(receptor=RECEPTOR, text="سفارش شما ثبت شد."))

    result = sms.send_bulk(
        BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text="فروشگاه فردا تعطیل است.")
    )
    # SMS.ir prices the batch rather than the message, so the total is on the result and each
    # entry's own `cost` is None. `packId` is the only handle that can cancel a scheduled send.
    assert isinstance(result.details, SmsIrDetails)
    print(f"{len(result)} accepted for {result.cost} credits, pack {result.details.pack_id}")

    sms.send_pattern(PatternMessage(receptor=RECEPTOR, pattern="100000", tokens={"CODE": "12345"}))


# ---------------------------------------------------------------------------------------------
# 6. The same three calls on Melipayamak
# ---------------------------------------------------------------------------------------------


def the_same_code_on_melipayamak(api_key: str) -> None:
    """Melipayamak's console API — the one that takes an API key.

    Not the older ``rest.payamak-panel.com`` API that Melipayamak's own samples use: that one
    authenticates with a username and password, takes recipients as a comma-joined string, and
    returns a single id for the whole batch rather than one per recipient.

    Two things behave differently here and are worth reading before you rely on them:

    * **`send_at` is refused.** Scheduling is a separate endpoint this SDK does not wrap, so
      accepting it would send the message *immediately* — the one failure a caller scheduling a
      message would never check for.
    * **Errors have no numeric code.** Melipayamak answers with a Persian sentence, so
      ``ProviderError.code`` is ``None`` and the message is what carries the meaning.
    """
    sms = MelipayamakSync(api_key, sender="50004001")

    sms.send(SmsMessage(receptor=RECEPTOR, text="سفارش شما ثبت شد."))
    sms.send_bulk(
        BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text="فروشگاه فردا تعطیل است.")
    )
    sms.send_pattern(PatternMessage(receptor=RECEPTOR, pattern="524", tokens=["12345"]))


def pattern_tokens_across_providers() -> tuple[PatternMessage, PatternMessage, PatternMessage]:
    """The one place the providers genuinely disagree about the shape of the input.

    Kavenegar's placeholders are numbered (``%token``, ``%token2``) and it takes either form.
    SMS.ir's are named (``#CODE#``) and it takes **only** a mapping. Melipayamak's ``args`` is a
    bare array filled in order and it takes **only** a sequence. Those last two are genuine
    opposites, so there is no portable form — passing the wrong one is refused before the request
    goes out rather than silently putting the right value in the wrong placeholder.

    In practice this costs little: the templates themselves live in each provider's own panel, so
    switching providers already means re-creating them.
    """
    kavenegar = PatternMessage(receptor=RECEPTOR, pattern="verify", tokens=["12345"])
    smsir = PatternMessage(receptor=RECEPTOR, pattern="100000", tokens={"CODE": "12345"})
    melipayamak = PatternMessage(receptor=RECEPTOR, pattern="524", tokens=["12345"])
    return kavenegar, smsir, melipayamak


# ---------------------------------------------------------------------------------------------


def main() -> None:
    api_key = os.environ.get("KAVENEGAR_API_KEY", "")
    if not api_key:
        print(
            "Set KAVENEGAR_API_KEY to run this against Kavenegar.\n"
            "There is no sandbox: every send is a real, billed message.\n"
            f"Providers wired up: {', '.join(available())}"
        )
        return

    print(f"sending one message to {RECEPTOR} …")
    try:
        send_one(api_key)
    except SmsError as exc:
        print(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
