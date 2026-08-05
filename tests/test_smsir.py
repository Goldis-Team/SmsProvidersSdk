"""SMS.ir, both engines, against a real HTTP server.

Every test that exercises the sync class has an async twin with the same fixtures. That pairing is
what keeps the two engines from drifting apart — a change that breaks one and not the other shows
up here rather than in production.
"""

from decimal import Decimal

import pytest

from sms_providers_sdk import (
    BulkSmsMessage,
    ConfigurationError,
    NetworkError,
    PatternMessage,
    ProviderError,
    SmsIrAsync,
    SmsIrSync,
    SmsMessage,
    available,
    get_async_provider,
    get_sync_provider,
)
from sms_providers_sdk.common.interfaces import IAsyncSmsProvider, ISyncSmsProvider
from sms_providers_sdk.providers.smsir import SmsIrDetails
from tests.conftest import Stub

API_KEY = "smsir-key-0123456789abcdef"
LINE = "30007487"
BULK = "/v1/send/bulk"
VERIFY = "/v1/send/verify"
RECEPTOR = "09121234567"
TEXT = "سفارش شما ثبت شد."


def bulk_data(*message_ids: int, cost: object = 1.0, pack_id: str = "pack-1") -> dict[str, object]:
    return {
        "status": 1,
        "message": "موفق",
        "data": {"packId": pack_id, "messageIds": list(message_ids), "cost": cost},
    }


def verify_data(message_id: int = 89545112, cost: object = 1.0) -> dict[str, object]:
    return {
        "status": 1,
        "message": "موفق",
        "data": {"messageId": message_id, "cost": cost},
    }


def a_provider(**overrides: object) -> SmsIrSync:
    options: dict[str, object] = {"line_number": LINE}
    options.update(overrides)
    return SmsIrSync(API_KEY, **options)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------------
# Single send — SMS.ir has no one-recipient endpoint, so this is send/bulk with one number
# ---------------------------------------------------------------------------------------------


def test_send_sync(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(500))
    result = a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))

    assert result.message_id == "500"
    assert result.receptors == (RECEPTOR,)
    assert result.cost == Decimal("1.0")

    sent = stub.last(BULK).json
    assert sent == {"lineNumber": 30007487, "messageText": TEXT, "mobiles": [RECEPTOR]}


async def test_send_async(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(500))
    result = await SmsIrAsync(API_KEY, line_number=LINE).send(
        SmsMessage(receptor=RECEPTOR, text=TEXT)
    )
    assert result.message_id == "500"
    assert stub.last(BULK).json["mobiles"] == [RECEPTOR]


def test_the_api_key_travels_in_a_header(stub: Stub) -> None:
    """Unlike Kavenegar, SMS.ir keeps the credential out of the URL."""
    stub.reply(BULK, bulk_data(500))
    a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    exchange = stub.last(BULK)
    assert exchange.headers["x-api-key"] == API_KEY
    assert API_KEY not in exchange.path


async def test_the_api_key_travels_in_a_header_on_both_engines(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(500))
    await SmsIrAsync(API_KEY, line_number=LINE).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert stub.last(BULK).headers["x-api-key"] == API_KEY


def test_the_body_is_json(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(500))
    a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert "application/json" in stub.last(BULK).headers["content-type"]


async def test_the_body_is_json_on_both_engines(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(500))
    await SmsIrAsync(API_KEY, line_number=LINE).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert "application/json" in stub.last(BULK).headers["content-type"]


def test_the_line_is_sent_as_a_number(stub: Stub) -> None:
    """SMS.ir declares ``lineNumber`` as a Long, not a string."""
    stub.reply(BULK, bulk_data(500))
    a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert stub.last(BULK).json["lineNumber"] == 30007487


def test_per_message_sender_beats_the_configured_line(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(500))
    a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT, sender="30008888"))
    assert stub.last(BULK).json["lineNumber"] == 30008888


def test_a_missing_line_is_refused_before_sending(stub: Stub) -> None:
    """SMS.ir has no account-level default line, and answers a missing one with a bare 101."""
    with pytest.raises(ConfigurationError, match="no account default"):
        SmsIrSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert stub.paths == []


def test_a_non_numeric_line_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="numeric line number"):
        SmsIrSync(API_KEY, line_number="my-line").send(SmsMessage(receptor=RECEPTOR, text=TEXT))


def test_scheduling_is_sent(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(500))
    a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT, send_at=1893456000))
    assert stub.last(BULK).json["sendDateTime"] == 1893456000


def test_extra_reaches_the_payload(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(500))
    a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT, extra={"someFutureField": 7}))
    assert stub.last(BULK).json["someFutureField"] == 7


def test_recipients_are_normalised(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(500))
    a_provider().send(SmsMessage(receptor="+98 912 123 4567", text=TEXT))
    assert stub.last(BULK).json["mobiles"] == [RECEPTOR]


def test_an_empty_message_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="empty message"):
        a_provider().send(SmsMessage(receptor=RECEPTOR, text="   "))


# ---------------------------------------------------------------------------------------------
# Bulk send
# ---------------------------------------------------------------------------------------------


def test_send_bulk_sync(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(501, 502, cost=2.5))
    result = a_provider().send_bulk(
        BulkSmsMessage(receptors=["0912 123 4567", "۰۹۳۵۱۲۳۴۵۶۷"], text=TEXT)
    )

    assert result.message_ids == ("501", "502")
    assert result.receptors == (RECEPTOR, "09351234567")
    assert result.cost == Decimal("2.5")
    assert stub.last(BULK).json["mobiles"] == [RECEPTOR, "09351234567"]


async def test_send_bulk_async(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(501, 502))
    result = await SmsIrAsync(API_KEY, line_number=LINE).send_bulk(
        BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text=TEXT)
    )
    assert result.message_ids == ("501", "502")


def test_bulk_cost_is_on_the_result_not_the_messages(stub: Stub) -> None:
    """SMS.ir prices the batch, not the message. Splitting the total across recipients would be
    inventing a per-message figure it never reported."""
    stub.reply(BULK, bulk_data(501, 502, cost=2.5))
    result = a_provider().send_bulk(BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text=TEXT))
    assert result.cost == Decimal("2.5")
    assert all(entry.cost is None for entry in result)


def test_a_fractional_cost_keeps_its_exact_value(stub: Stub) -> None:
    """Built from the text, not from the float json produced — ``Decimal(1.1)`` is not ``1.1``."""
    stub.reply(BULK, bulk_data(501, cost=1.1))
    result = a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert result.cost == Decimal("1.1")


def test_ids_are_left_unpaired_when_the_counts_disagree(stub: Stub) -> None:
    """Pairing is positional, so a count mismatch makes it unknowable. An id attributed to the
    wrong number is worse than one attributed to nobody."""
    stub.reply(BULK, bulk_data(501))
    result = a_provider().send_bulk(BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text=TEXT))
    assert result.message_ids == ("501",)
    assert result.receptors == ("",)


def test_an_empty_batch_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="empty recipient list"):
        a_provider().send_bulk(BulkSmsMessage(receptors=[], text=TEXT))


def test_an_oversized_batch_is_refused_before_sending(stub: Stub) -> None:
    """SMS.ir's cap is 100 — half Kavenegar's — and it rejects the batch whole."""
    with pytest.raises(ConfigurationError, match="at most 100 recipients"):
        a_provider().send_bulk(BulkSmsMessage(receptors=[RECEPTOR] * 101, text=TEXT))
    assert stub.paths == []


def test_local_ids_are_refused(stub: Stub) -> None:
    """SMS.ir has no client-supplied reference. Accepting one would send it into a void."""
    with pytest.raises(ConfigurationError, match="no client-supplied message id"):
        a_provider().send_bulk(
            BulkSmsMessage(receptors=[RECEPTOR], text=TEXT, local_ids=["order-1"])
        )


def test_the_pack_id_comes_back_on_details(stub: Stub) -> None:
    """The only handle that can cancel a scheduled send."""
    stub.reply(BULK, bulk_data(501, pack_id="7f3a-…"))
    result = a_provider().send_bulk(BulkSmsMessage(receptors=[RECEPTOR], text=TEXT))
    assert isinstance(result.details, SmsIrDetails)
    assert result.details.pack_id == "7f3a-…"


# ---------------------------------------------------------------------------------------------
# Pattern send
# ---------------------------------------------------------------------------------------------


def test_send_pattern_sync(stub: Stub) -> None:
    stub.reply(VERIFY, verify_data())
    result = a_provider().send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="100000", tokens={"CODE": "12345"})
    )

    assert result.message_id == "89545112"
    assert result.cost == Decimal("1.0")
    assert stub.last(VERIFY).json == {
        "mobile": RECEPTOR,
        "templateId": 100000,
        "parameters": [{"name": "CODE", "value": "12345"}],
    }


async def test_send_pattern_async(stub: Stub) -> None:
    stub.reply(VERIFY, verify_data())
    result = await SmsIrAsync(API_KEY, line_number=LINE).send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="100000", tokens={"CODE": "12345"})
    )
    assert result.message_id == "89545112"


def test_a_pattern_send_costs_the_same_on_the_result_and_the_message(stub: Stub) -> None:
    """One recipient, so the call's cost and the message's cost are the same number."""
    stub.reply(VERIFY, verify_data(cost=1.0))
    result = a_provider().send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="100000", tokens={"CODE": "1"})
    )
    assert result.first is not None
    assert result.first.cost == result.cost == Decimal("1.0")


def test_positional_tokens_are_refused(stub: Stub) -> None:
    """SMS.ir placeholders are ``#NAME#`` and the API matches on the name. There is no ordering to
    fall back on, and guessing one puts the right value in the wrong slot of a sent message."""
    with pytest.raises(ConfigurationError, match="named parameters"):
        a_provider().send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="100000", tokens=["12345"])
        )
    assert stub.paths == []


def test_a_template_with_no_parameters_is_fine(stub: Stub) -> None:
    stub.reply(VERIFY, verify_data())
    a_provider().send_pattern(PatternMessage(receptor=RECEPTOR, pattern="100000"))
    assert stub.last(VERIFY).json["parameters"] == []


def test_a_non_numeric_template_is_refused(stub: Stub) -> None:
    """SMS.ir identifies templates by id; Kavenegar by name. Passing one to the other is the
    obvious mistake when switching providers."""
    with pytest.raises(ConfigurationError, match="numeric id"):
        a_provider().send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="verify", tokens={"CODE": "1"})
        )


def test_an_overlong_parameter_is_refused(stub: Stub) -> None:
    """25 characters is short enough that a full name overruns it."""
    with pytest.raises(ConfigurationError, match="25 characters; NAME is 26"):
        a_provider().send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="100000", tokens={"NAME": "x" * 26})
        )


def test_an_empty_parameter_name_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="empty parameter name"):
        a_provider().send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="100000", tokens={"  ": "1"})
        )


def test_a_pattern_send_refuses_a_sender(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="no line parameter"):
        a_provider().send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="100000", tokens={"CODE": "1"}, sender=LINE)
        )


# ---------------------------------------------------------------------------------------------
# Refusals and failures
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "http_status", "expected"),
    [
        (10, 401, "invalid API key"),
        (102, 400, "insufficient credit"),
        (105, 400, "too many mobile numbers"),
        (113, 400, "template not found"),
        (115, 400, "blacklist"),
        (20, 429, "rate limit exceeded"),
    ],
)
def test_a_refusal_raises_with_the_code_and_an_english_reason(
    stub: Stub, status: int, http_status: int, expected: str
) -> None:
    """SMS.ir mirrors its business failure into the HTTP status. The body is the useful part, so
    the transport decodes it regardless of what the status line said."""
    stub.reply(BULK, {"status": status, "message": "خطا", "data": None}, status=http_status)
    with pytest.raises(ProviderError) as exc:
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))

    assert exc.value.code == status
    assert expected in str(exc.value)
    assert exc.value.raw["message"] == "خطا"


async def test_a_refusal_raises_on_the_async_engine_too(stub: Stub) -> None:
    stub.reply(BULK, {"status": 102, "message": "خطا"}, status=400)
    with pytest.raises(ProviderError) as exc:
        await SmsIrAsync(API_KEY, line_number=LINE).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert exc.value.code == 102


def test_an_unknown_status_still_raises_with_what_smsir_said(stub: Stub) -> None:
    stub.reply(BULK, {"status": 999, "message": "یک خطای تازه"})
    with pytest.raises(ProviderError) as exc:
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert exc.value.code == 999
    assert "یک خطای تازه" in str(exc.value)


def test_an_accepted_call_with_no_ids_raises(stub: Stub) -> None:
    stub.reply(BULK, {"status": 1, "message": "موفق", "data": {"messageIds": []}})
    with pytest.raises(ProviderError, match="nothing was sent"):
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))


def test_an_accepted_pattern_call_with_no_id_raises(stub: Stub) -> None:
    stub.reply(VERIFY, {"status": 1, "message": "موفق", "data": {}})
    with pytest.raises(ProviderError, match="nothing was sent"):
        a_provider().send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="100000", tokens={"CODE": "1"})
        )


def test_a_non_json_body_is_a_network_error(stub: Stub) -> None:
    stub.reply_text(BULK, "<html>502 Bad Gateway</html>", status=502)
    with pytest.raises(NetworkError, match="non-JSON"):
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))


async def test_a_non_json_body_is_a_network_error_async(stub: Stub) -> None:
    stub.reply_text(BULK, "<html>502 Bad Gateway</html>", status=502)
    with pytest.raises(NetworkError, match="non-JSON"):
        await SmsIrAsync(API_KEY, line_number=LINE).send(SmsMessage(receptor=RECEPTOR, text=TEXT))


def test_an_empty_api_key_fails_at_construction() -> None:
    with pytest.raises(ConfigurationError, match="api_key"):
        SmsIrSync("   ")


def test_the_api_key_is_not_in_the_config_repr() -> None:
    assert API_KEY not in repr(a_provider().config)


def test_details_carry_the_status(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(500))
    result = a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert isinstance(result.details, SmsIrDetails)
    assert result.details.status == 1
    assert result.details.status_message == "موفق"
    assert result.details.status_description == "successful"


# ---------------------------------------------------------------------------------------------
# Registry and protocols
# ---------------------------------------------------------------------------------------------


def test_the_registry_knows_smsir() -> None:
    """The full list is asserted once, in ``test_melipayamak.py``."""
    assert "smsir" in available()


def test_both_engines_are_reachable_by_name(stub: Stub) -> None:
    stub.reply(BULK, bulk_data(500))
    provider = get_sync_provider("smsir", api_key=API_KEY, line_number=LINE)
    assert provider.send(SmsMessage(receptor=RECEPTOR, text=TEXT)).message_id == "500"
    assert isinstance(get_async_provider("smsir", api_key=API_KEY), SmsIrAsync)


def test_the_classes_satisfy_their_protocols() -> None:
    assert isinstance(a_provider(), ISyncSmsProvider)
    assert isinstance(SmsIrAsync(API_KEY), IAsyncSmsProvider)
