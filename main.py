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


def send_one(api_key: str, line: str) -> str:
    sms = KavenegarSync(api_key, sender=line)
    result = sms.send(SmsMessage(receptor=RECEPTOR, text="سفارش شما ثبت شد."))

    entry = result.first
    assert entry is not None
    print(f"sent {entry.message_id} from {entry.sender} for {entry.cost}")
    return entry.message_id


def send_to_a_group(api_key: str, line: str, numbers: list[str]) -> SmsResult:
    result = KavenegarSync(api_key, sender=line).send_bulk(
        BulkSmsMessage(
            receptors=numbers,
            text="فروشگاه فردا تعطیل است.",
            extra={"hide": 1},
        )
    )
    print(f"{len(result)} accepted, total cost {result.cost}")
    return result


def send_a_one_time_code(api_key: str, code: str) -> str:
    result = KavenegarSync(api_key).send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="verify", tokens=[code])
    )
    entry = result.first
    assert entry is not None
    print(f"code sent as {entry.message_id}; rendered text: {entry.text}")
    return entry.message_id


def scheduled_and_traceable(api_key: str, line: str, when: int) -> SmsResult:
    return KavenegarSync(api_key, sender=line).send(
        SmsMessage(
            receptor=RECEPTOR,
            text="یادآوری نوبت فردا ساعت ۱۰.",
            send_at=when,
            local_id="appointment-8842",
        )
    )


async def send_one_async(api_key: str, line: str) -> str:
    """The same call, awaited. Same arguments, same result type."""
    sms = KavenegarAsync(api_key, sender=line)
    result = await sms.send(SmsMessage(receptor=RECEPTOR, text="سفارش شما ثبت شد."))
    return result.message_id or ""


async def send_several_concurrently(api_key: str, line: str, texts: list[str]) -> list[SmsResult]:
    sms = KavenegarAsync(api_key, sender=line)
    return await asyncio.gather(
        *(sms.send(SmsMessage(receptor=RECEPTOR, text=text)) for text in texts)
    )


def send_carefully(api_key: str, line: str, text: str) -> str | None:
    try:
        result = KavenegarSync(api_key, sender=line).send(SmsMessage(receptor=RECEPTOR, text=text))
    except ConfigurationError as exc:
        print(f"bad input: {exc}")
        return None
    except ProviderError as exc:
        print(f"refused with code {exc.code}: {exc}")
        return None
    except NetworkError as exc:
        print(f"unreachable: {exc}")
        return None
    return result.message_id


def status_of_each_recipient(result: SmsResult) -> None:
    for entry in result:
        print(f"{entry.receptor}: {entry.status_text} (id {entry.message_id})")


def from_configuration(name: str, api_key: str, line: str) -> str | None:
    print(f"available: {', '.join(available())}")
    sms = get_sync_provider(name, api_key=api_key, sender=line)
    return sms.send(SmsMessage(receptor=RECEPTOR, text="سلام")).message_id


async def from_configuration_async(name: str, api_key: str, line: str) -> str | None:
    sms = get_async_provider(name, api_key=api_key, sender=line)
    result = await sms.send(SmsMessage(receptor=RECEPTOR, text="سلام"))
    return result.message_id


def the_same_code_on_smsir(api_key: str) -> None:
    sms = SmsIrSync(api_key, line_number="30007487")

    sms.send(SmsMessage(receptor=RECEPTOR, text="سفارش شما ثبت شد."))

    result = sms.send_bulk(
        BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text="فروشگاه فردا تعطیل است.")
    )
    assert isinstance(result.details, SmsIrDetails)
    print(f"{len(result)} accepted for {result.cost} credits, pack {result.details.pack_id}")

    sms.send_pattern(PatternMessage(receptor=RECEPTOR, pattern="100000", tokens={"CODE": "12345"}))


def the_same_code_on_melipayamak(api_key: str) -> None:
    sms = MelipayamakSync(api_key, sender="50004001")

    sms.send(SmsMessage(receptor=RECEPTOR, text="سفارش شما ثبت شد."))
    sms.send_bulk(
        BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text="فروشگاه فردا تعطیل است.")
    )
    sms.send_pattern(PatternMessage(receptor=RECEPTOR, pattern="524", tokens=["12345"]))


def pattern_tokens_across_providers() -> tuple[PatternMessage, PatternMessage, PatternMessage]:
    kavenegar = PatternMessage(receptor=RECEPTOR, pattern="verify", tokens=["12345"])
    smsir = PatternMessage(receptor=RECEPTOR, pattern="100000", tokens={"CODE": "12345"})
    melipayamak = PatternMessage(receptor=RECEPTOR, pattern="524", tokens=["12345"])
    return kavenegar, smsir, melipayamak


def main() -> None:
    api_key = os.environ.get("KAVENEGAR_API_KEY", "")
    line = os.environ.get("KAVENEGAR_LINE", "")
    if not api_key or not line:
        print(
            "Set KAVENEGAR_API_KEY and KAVENEGAR_LINE to run this against Kavenegar.\n"
            "The line is required: Kavenegar's account-level default sender is unset unless\n"
            "someone configured it, and omitting the line then fails with a 412 that names a\n"
            "value you never passed.\n"
            "There is no sandbox: every send is a real, billed message.\n"
            f"Providers wired up: {', '.join(available())}"
        )
        return

    print(f"sending one message to {RECEPTOR} from {line} …")
    try:
        send_one(api_key, line)
    except SmsError as exc:
        print(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
