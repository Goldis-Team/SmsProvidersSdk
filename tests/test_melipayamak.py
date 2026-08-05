"""Melipayamak (console API), both engines, against a real HTTP server.

Every test that exercises the sync class has an async twin with the same fixtures. That pairing is
what keeps the two engines from drifting apart — a change that breaks one and not the other shows
up here rather than in production.
"""

import socket

import pytest

from sms_providers_sdk import (
    BulkSmsMessage,
    ConfigurationError,
    MelipayamakAsync,
    MelipayamakSync,
    NetworkError,
    PatternMessage,
    ProviderError,
    SmsMessage,
    available,
    get_async_provider,
    get_sync_provider,
)
from sms_providers_sdk.common.interfaces import IAsyncSmsProvider, ISyncSmsProvider
from sms_providers_sdk.providers.melipayamak import MelipayamakDetails
from sms_providers_sdk.providers.melipayamak import helpers as melipayamak_helpers
from tests.conftest import Stub

API_KEY = "9f2c4a1e8b7d6053a1c2e3f4b5a69788"
LINE = "50004001"
SIMPLE = "/send/simple/"
ADVANCED = "/send/advanced/"
SHARED = "/send/shared/"
RECEPTOR = "09121234567"
TEXT = "سفارش شما ثبت شد."

#: Melipayamak's ids are 64-bit and its own examples already exceed int32.
REC_ID = 3741437414
REC_ID_2 = 3741437415

#: What Melipayamak's docs literally show for `status`: "description of the error, if one occurs".
#: Its value on a *successful* send is unspecified, which is why nothing here matches against it.
STATUS_PLACEHOLDER = "شرح خطا در صورت بروز"


def a_provider(**overrides: object) -> MelipayamakSync:
    options: dict[str, object] = {"sender": LINE}
    options.update(overrides)
    return MelipayamakSync(API_KEY, **options)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------------
# Single send
# ---------------------------------------------------------------------------------------------


def test_send_sync(stub: Stub) -> None:
    stub.reply(SIMPLE, {"recId": REC_ID, "status": STATUS_PLACEHOLDER})
    result = a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))

    assert result.message_id == "3741437414"
    assert result.receptors == (RECEPTOR,)
    assert result.cost is None  # Melipayamak reports none on either send endpoint

    assert stub.last(SIMPLE).json == {"from": LINE, "to": RECEPTOR, "text": TEXT}


async def test_send_async(stub: Stub) -> None:
    stub.reply(SIMPLE, {"recId": REC_ID, "status": None})
    result = await MelipayamakAsync(API_KEY, sender=LINE).send(
        SmsMessage(receptor=RECEPTOR, text=TEXT)
    )
    assert result.message_id == "3741437414"


def test_a_big_id_survives_intact(stub: Stub) -> None:
    """Melipayamak's ids run past 2^53, where a JavaScript client silently corrupts them. Python's
    integers are arbitrary-precision, so the only requirement is not to round-trip through float."""
    huge = 9007199254740993  # 2**53 + 1
    stub.reply(SIMPLE, {"recId": huge, "status": None})
    result = a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert result.message_id == "9007199254740993"


def test_the_api_key_is_the_last_path_segment(stub: Stub) -> None:
    stub.reply(SIMPLE, {"recId": REC_ID})
    a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert stub.last().path == f"/api/send/simple/{API_KEY}"


def test_the_body_is_json(stub: Stub) -> None:
    stub.reply(SIMPLE, {"recId": REC_ID})
    a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert "application/json" in stub.last(SIMPLE).headers["content-type"]


async def test_the_body_is_json_on_both_engines(stub: Stub) -> None:
    stub.reply(SIMPLE, {"recId": REC_ID})
    await MelipayamakAsync(API_KEY, sender=LINE).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert "application/json" in stub.last(SIMPLE).headers["content-type"]


def test_per_message_sender_beats_the_configured_line(stub: Stub) -> None:
    stub.reply(SIMPLE, {"recId": REC_ID})
    a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT, sender="50008888"))
    assert stub.last(SIMPLE).json["from"] == "50008888"


def test_a_missing_line_is_refused_before_sending(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="requires a sending line"):
        MelipayamakSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert stub.paths == []


def test_recipients_are_normalised(stub: Stub) -> None:
    stub.reply(SIMPLE, {"recId": REC_ID})
    a_provider().send(SmsMessage(receptor="+98 912 123 4567", text=TEXT))
    assert stub.last(SIMPLE).json["to"] == RECEPTOR


def test_an_empty_message_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="empty message"):
        a_provider().send(SmsMessage(receptor=RECEPTOR, text="  "))


def test_extra_reaches_the_payload(stub: Stub) -> None:
    stub.reply(SIMPLE, {"recId": REC_ID})
    a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT, extra={"udh": "0605040B8423F0"}))
    assert stub.last(SIMPLE).json["udh"] == "0605040B8423F0"


# ---------------------------------------------------------------------------------------------
# What Melipayamak has nowhere to put
# ---------------------------------------------------------------------------------------------


def test_scheduling_is_refused_rather_than_dropped(stub: Stub) -> None:
    """Scheduling is a separate ``send/schedule`` method. Dropping ``send_at`` here would send the
    message immediately — the one failure a caller scheduling a message would never check for."""
    with pytest.raises(ConfigurationError, match="send the message immediately instead"):
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT, send_at=1893456000))
    assert stub.paths == []


def test_a_local_id_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="no client-supplied message id"):
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT, local_id="order-1"))


def test_bulk_local_ids_are_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="no client-supplied message id"):
        a_provider().send_bulk(
            BulkSmsMessage(receptors=[RECEPTOR], text=TEXT, local_ids=["order-1"])
        )


# ---------------------------------------------------------------------------------------------
# Bulk send
# ---------------------------------------------------------------------------------------------


def test_send_bulk_sync(stub: Stub) -> None:
    stub.reply(ADVANCED, {"recIds": [REC_ID, REC_ID_2], "status": None})
    result = a_provider().send_bulk(
        BulkSmsMessage(receptors=["0912 123 4567", "۰۹۳۵۱۲۳۴۵۶۷"], text=TEXT)
    )

    assert result.message_ids == ("3741437414", "3741437415")
    assert result.receptors == (RECEPTOR, "09351234567")
    assert stub.last(ADVANCED).json == {
        "from": LINE,
        "to": [RECEPTOR, "09351234567"],
        "text": TEXT,
    }


async def test_send_bulk_async(stub: Stub) -> None:
    stub.reply(ADVANCED, {"recIds": [REC_ID, REC_ID_2]})
    result = await MelipayamakAsync(API_KEY, sender=LINE).send_bulk(
        BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text=TEXT)
    )
    assert result.message_ids == ("3741437414", "3741437415")


def test_recipients_are_sent_as_a_json_array(stub: Stub) -> None:
    """``to`` is declared ``System.String[]`` — a comma-joined string is rejected by the
    deserialiser, which is what the legacy payamak-panel API wanted instead."""
    stub.reply(ADVANCED, {"recIds": [REC_ID]})
    a_provider().send_bulk(BulkSmsMessage(receptors=[RECEPTOR], text=TEXT))
    assert stub.last(ADVANCED).json["to"] == [RECEPTOR]


def test_ids_are_left_unpaired_when_the_counts_disagree(stub: Stub) -> None:
    """No source states the length-and-order guarantee outright, so a mismatch is not guessed at."""
    stub.reply(ADVANCED, {"recIds": [REC_ID]})
    result = a_provider().send_bulk(BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text=TEXT))
    assert result.message_ids == ("3741437414",)
    assert result.receptors == ("",)


def test_an_empty_batch_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="empty recipient list"):
        a_provider().send_bulk(BulkSmsMessage(receptors=[], text=TEXT))


def test_a_large_batch_is_not_capped_locally(stub: Stub) -> None:
    """Melipayamak documents no recipient limit for this endpoint. Inventing one would refuse
    batches the account is entitled to send; if there is a limit, its own error is the accurate
    one."""
    stub.reply(ADVANCED, {"recIds": [REC_ID] * 300})
    result = a_provider().send_bulk(BulkSmsMessage(receptors=[RECEPTOR] * 300, text=TEXT))
    assert len(result) == 300


# ---------------------------------------------------------------------------------------------
# Pattern send
# ---------------------------------------------------------------------------------------------


def test_send_pattern_sync(stub: Stub) -> None:
    stub.reply(SHARED, {"recId": REC_ID, "status": None})
    result = a_provider().send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="524", tokens=["12345", "علی"])
    )

    assert result.message_id == "3741437414"
    assert stub.last(SHARED).json == {
        "bodyId": 524,
        "to": RECEPTOR,
        "args": ["12345", "علی"],
    }


async def test_send_pattern_async(stub: Stub) -> None:
    stub.reply(SHARED, {"recId": REC_ID})
    result = await MelipayamakAsync(API_KEY, sender=LINE).send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="524", tokens=["12345"])
    )
    assert result.message_id == "3741437414"


def test_the_body_id_is_sent_as_an_integer(stub: Stub) -> None:
    stub.reply(SHARED, {"recId": REC_ID})
    a_provider().send_pattern(PatternMessage(receptor=RECEPTOR, pattern="524", tokens=["1"]))
    assert stub.last(SHARED).json["bodyId"] == 524


def test_named_tokens_are_refused(stub: Stub) -> None:
    """The mirror of SMS.ir. Melipayamak's ``args`` is a bare array filled in order, so a mapping's
    keys would be dropped and its values sent in an order the caller never chose."""
    with pytest.raises(ConfigurationError, match="positional arguments"):
        a_provider().send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="524", tokens={"CODE": "12345"})
        )
    assert stub.paths == []


def test_a_template_with_no_arguments_is_fine(stub: Stub) -> None:
    stub.reply(SHARED, {"recId": REC_ID})
    a_provider().send_pattern(PatternMessage(receptor=RECEPTOR, pattern="524"))
    assert stub.last(SHARED).json["args"] == []


def test_a_non_numeric_template_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="numeric bodyId"):
        a_provider().send_pattern(PatternMessage(receptor=RECEPTOR, pattern="verify"))


def test_a_body_id_beyond_int32_is_refused(stub: Stub) -> None:
    """``bodyId`` is ``System.Int32``; anything larger is rejected by the deserialiser with an
    error that talks about JSON conversion rather than about the template."""
    with pytest.raises(ConfigurationError, match="32-bit integer"):
        a_provider().send_pattern(PatternMessage(receptor=RECEPTOR, pattern="2147483648"))


def test_a_pattern_send_refuses_a_sender(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="no line parameter"):
        a_provider().send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="524", tokens=["1"], sender=LINE)
        )


# ---------------------------------------------------------------------------------------------
# Refusals and failures
# ---------------------------------------------------------------------------------------------


def test_a_refusal_raises_with_melipayamaks_own_words(stub: Stub) -> None:
    """An application-level refusal is HTTP 400 with a Persian ``status`` and no ``recId`` key."""
    stub.reply(SIMPLE, {"status": "کلید کنسول معتبر نیست"}, status=400)
    with pytest.raises(ProviderError) as exc:
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))

    assert "کلید کنسول معتبر نیست" in str(exc.value)
    assert exc.value.raw["status"] == "کلید کنسول معتبر نیست"


async def test_a_refusal_raises_on_the_async_engine_too(stub: Stub) -> None:
    stub.reply(SIMPLE, {"status": "کلید کنسول معتبر نیست"}, status=400)
    with pytest.raises(ProviderError, match="کلید کنسول معتبر نیست"):
        await MelipayamakAsync(API_KEY, sender=LINE).send(SmsMessage(receptor=RECEPTOR, text=TEXT))


def test_a_refusal_carries_no_numeric_code(stub: Stub) -> None:
    """Melipayamak reports failures as sentences, not numbers. Passing the HTTP status off as a
    provider code would give callers something to branch on that it never promised to keep."""
    stub.reply(SIMPLE, {"status": "اعتبار کافی نیست"}, status=400)
    with pytest.raises(ProviderError) as exc:
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert exc.value.code is None


def test_a_bulk_refusal_raises(stub: Stub) -> None:
    stub.reply(ADVANCED, {"status": "کلید کنسول معتبر نیست"}, status=400)
    with pytest.raises(ProviderError, match="کلید کنسول معتبر نیست"):
        a_provider().send_bulk(BulkSmsMessage(receptors=[RECEPTOR], text=TEXT))


def test_a_problem_details_body_is_read_for_what_it_says(stub: Stub) -> None:
    """The other failure shape: ASP.NET's model binder answers before Melipayamak's code runs, and
    its ``status`` is the integer 400. Reading that as text would report the failure as "400"."""
    stub.reply(
        SIMPLE,
        {
            "type": "https://tools.ietf.org/html/rfc9110#section-15.5.1",
            "title": "One or more validation errors occurred.",
            "status": 400,
            "errors": {"$": ["missing required properties including: 'from', 'to', 'text'."]},
        },
        status=400,
    )
    with pytest.raises(ProviderError) as exc:
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))

    message = str(exc.value)
    assert "One or more validation errors occurred." in message
    assert "missing required properties" in message
    assert "400" not in message.replace("15.5.1", "")


def test_an_accepted_call_with_no_id_raises(stub: Stub) -> None:
    stub.reply(SIMPLE, {"status": None})
    with pytest.raises(ProviderError, match="no message id and gave no reason"):
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))


def test_a_bulk_call_with_an_empty_id_list_raises(stub: Stub) -> None:
    stub.reply(ADVANCED, {"recIds": [], "status": None})
    with pytest.raises(ProviderError, match="no message id"):
        a_provider().send_bulk(BulkSmsMessage(receptors=[RECEPTOR], text=TEXT))


def test_an_html_answer_is_a_network_error(stub: Stub) -> None:
    """A wrong method or path does not 404 — Melipayamak answers HTTP 200 with the console's own
    Angular page, so the transport has to decide on the body rather than on the status line."""
    stub.reply_text(SIMPLE, "<!doctype html><html><app-root></app-root></html>", status=200)
    with pytest.raises(NetworkError, match="non-JSON"):
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))


async def test_an_html_answer_is_a_network_error_async(stub: Stub) -> None:
    stub.reply_text(SIMPLE, "<!doctype html><html><app-root></app-root></html>", status=200)
    with pytest.raises(NetworkError, match="non-JSON"):
        await MelipayamakAsync(API_KEY, sender=LINE).send(SmsMessage(receptor=RECEPTOR, text=TEXT))


def test_an_empty_api_key_fails_at_construction() -> None:
    with pytest.raises(ConfigurationError, match="api_key"):
        MelipayamakSync("  ")


def test_details_carry_the_status_and_ids(stub: Stub) -> None:
    stub.reply(ADVANCED, {"recIds": [REC_ID, REC_ID_2], "status": STATUS_PLACEHOLDER})
    result = a_provider().send_bulk(BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text=TEXT))
    assert isinstance(result.details, MelipayamakDetails)
    assert result.details.status_message == STATUS_PLACEHOLDER
    assert result.details.rec_ids == ("3741437414", "3741437415")


# ---------------------------------------------------------------------------------------------
# The API key must not leak
# ---------------------------------------------------------------------------------------------


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    return port


def test_the_api_key_is_scrubbed_from_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(melipayamak_helpers, "BASE_URL", f"http://127.0.0.1:{_closed_port()}/api")
    with pytest.raises(NetworkError) as exc:
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert API_KEY not in str(exc.value)


async def test_the_api_key_is_scrubbed_on_the_async_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(melipayamak_helpers, "BASE_URL", f"http://127.0.0.1:{_closed_port()}/api")
    with pytest.raises(NetworkError) as exc:
        await MelipayamakAsync(API_KEY, sender=LINE).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert API_KEY not in str(exc.value)


def test_the_api_key_is_scrubbed_from_an_html_body(stub: Stub) -> None:
    stub.reply_text(SIMPLE, f"<html>no route for /api/send/simple/{API_KEY}</html>", status=200)
    with pytest.raises(NetworkError) as exc:
        a_provider().send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert API_KEY not in str(exc.value)
    assert "***" in str(exc.value)


def test_the_api_key_is_not_in_the_config_repr() -> None:
    assert API_KEY not in repr(a_provider().config)


# ---------------------------------------------------------------------------------------------
# Registry and protocols
# ---------------------------------------------------------------------------------------------


def test_the_registry_lists_every_provider() -> None:
    assert available() == ("kavenegar", "melipayamak", "smsir")


def test_both_engines_are_reachable_by_name(stub: Stub) -> None:
    stub.reply(SIMPLE, {"recId": REC_ID})
    provider = get_sync_provider("melipayamak", api_key=API_KEY, sender=LINE)
    assert provider.send(SmsMessage(receptor=RECEPTOR, text=TEXT)).message_id == "3741437414"
    assert isinstance(get_async_provider("melipayamak", api_key=API_KEY), MelipayamakAsync)


def test_the_classes_satisfy_their_protocols() -> None:
    assert isinstance(a_provider(), ISyncSmsProvider)
    assert isinstance(MelipayamakAsync(API_KEY), IAsyncSmsProvider)
