"""Kavenegar, both engines, against a real HTTP server.

Every test that exercises the sync class has an async twin with the same fixtures. That pairing is
what keeps the two engines from drifting apart — a change that breaks one and not the other shows
up here rather than in production.
"""

import socket

import pytest

from sms_providers_sdk import (
    BulkSmsMessage,
    ConfigurationError,
    KavenegarAsync,
    KavenegarSync,
    NetworkError,
    PatternMessage,
    ProviderError,
    SmsMessage,
    available,
    get_async_provider,
    get_sync_provider,
)
from sms_providers_sdk.common.interfaces import IAsyncSmsProvider, ISyncSmsProvider
from sms_providers_sdk.providers.kavenegar import KavenegarDetails
from sms_providers_sdk.providers.kavenegar import helpers as kavenegar_helpers
from tests.conftest import Stub

API_KEY = "4b6b7a5a6f4d4c3b2a1908070605040302010009"
SEND = "/sms/send.json"
LOOKUP = "/verify/lookup.json"
RECEPTOR = "09121234567"
TEXT = "کد ورود شما ۱۲۳۴۵ است"

APPROVED = {"status": 200, "message": "تایید شد"}


def an_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "messageid": 8792343,
        "message": TEXT,
        "status": 1,
        "statustext": "در صف ارسال",
        "sender": "10004346",
        "receptor": RECEPTOR,
        "date": 1356619709,
        "cost": 120,
    }
    entry.update(overrides)
    return entry


def a_response(*entries: dict[str, object], **envelope: object) -> dict[str, object]:
    return {"return": {**APPROVED, **envelope}, "entries": list(entries)}


# ---------------------------------------------------------------------------------------------
# Single send
# ---------------------------------------------------------------------------------------------


def test_send_sync(stub: Stub) -> None:
    stub.reply(SEND, a_response(an_entry()))
    result = KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))

    assert result.message_id == "8792343"
    assert len(result) == 1
    assert result.cost == 120
    assert result.first is not None
    assert result.first.status == 1
    assert result.first.status_text == "در صف ارسال"
    assert result.first.sent_at == 1356619709

    sent = stub.last(SEND).form
    assert sent == {"receptor": RECEPTOR, "message": TEXT}


async def test_send_async(stub: Stub) -> None:
    stub.reply(SEND, a_response(an_entry()))
    result = await KavenegarAsync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))

    assert result.message_id == "8792343"
    assert stub.last(SEND).form["receptor"] == RECEPTOR


def test_send_puts_the_api_key_in_the_path(stub: Stub) -> None:
    stub.reply(SEND, a_response(an_entry()))
    KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert stub.last().path == f"/v1/{API_KEY}/sms/send.json"


def test_send_is_form_encoded_not_json(stub: Stub) -> None:
    """Kavenegar reads ``application/x-www-form-urlencoded`` and ignores a JSON body entirely."""
    stub.reply(SEND, a_response(an_entry()))
    KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert "x-www-form-urlencoded" in stub.last(SEND).headers["content-type"]


async def test_send_is_form_encoded_on_both_engines(stub: Stub) -> None:
    stub.reply(SEND, a_response(an_entry()))
    await KavenegarAsync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert "x-www-form-urlencoded" in stub.last(SEND).headers["content-type"]


def test_send_uses_the_configured_default_line(stub: Stub) -> None:
    stub.reply(SEND, a_response(an_entry()))
    KavenegarSync(API_KEY, sender="10004346").send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert stub.last(SEND).form["sender"] == "10004346"


def test_per_message_sender_beats_the_default(stub: Stub) -> None:
    stub.reply(SEND, a_response(an_entry()))
    KavenegarSync(API_KEY, sender="10004346").send(
        SmsMessage(receptor=RECEPTOR, text=TEXT, sender="2000500666")
    )
    assert stub.last(SEND).form["sender"] == "2000500666"


def test_scheduling_and_local_id_are_sent(stub: Stub) -> None:
    stub.reply(SEND, a_response(an_entry()))
    KavenegarSync(API_KEY).send(
        SmsMessage(receptor=RECEPTOR, text=TEXT, send_at=1893456000, local_id="order-42")
    )
    sent = stub.last(SEND).form
    assert sent["date"] == "1893456000"
    assert sent["localid"] == "order-42"


def test_extra_reaches_the_payload(stub: Stub) -> None:
    """The escape hatch for provider-specific parameters — ``hide``, ``type``, ``tag``."""
    stub.reply(SEND, a_response(an_entry()))
    KavenegarSync(API_KEY).send(
        SmsMessage(receptor=RECEPTOR, text=TEXT, extra={"type": 0, "tag": "welcome"})
    )
    sent = stub.last(SEND).form
    assert sent["type"] == "0"
    assert sent["tag"] == "welcome"


# ---------------------------------------------------------------------------------------------
# Recipient normalisation
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "given",
    [
        "09121234567",
        "0912 123 4567",
        "0912-123-4567",
        "+989121234567",
        "00989121234567",
        "989121234567",
        "۰۹۱۲۱۲۳۴۵۶۷",  # Persian digits
        "٠٩١٢١٢٣٤٥٦٧",  # Arabic-Indic digits
    ],
)
def test_recipients_are_normalised(stub: Stub, given: str) -> None:
    stub.reply(SEND, a_response(an_entry()))
    KavenegarSync(API_KEY).send(SmsMessage(receptor=given, text=TEXT))
    assert stub.last(SEND).form["receptor"] == RECEPTOR


def test_a_short_code_is_left_alone(stub: Stub) -> None:
    """``98…`` is only rewritten for a 12-digit mobile; a short code that happens to start with
    those digits is a real line and must not be turned into a phone number."""
    stub.reply(SEND, a_response(an_entry()))
    KavenegarSync(API_KEY).send(SmsMessage(receptor="9891234", text=TEXT))
    assert stub.last(SEND).form["receptor"] == "9891234"


def test_an_empty_recipient_never_reaches_the_wire(stub: Stub) -> None:
    with pytest.raises(ConfigurationError):
        KavenegarSync(API_KEY).send(SmsMessage(receptor="   ", text=TEXT))
    assert stub.paths == []


def test_a_non_numeric_recipient_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="non-numeric"):
        KavenegarSync(API_KEY).send(SmsMessage(receptor="0912abc4567", text=TEXT))


def test_an_empty_message_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="empty message"):
        KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text="   "))


def test_an_overlong_message_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="1800 characters"):
        KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text="x" * 1801))


# ---------------------------------------------------------------------------------------------
# Bulk send
# ---------------------------------------------------------------------------------------------


def test_send_bulk_sync(stub: Stub) -> None:
    stub.reply(
        SEND,
        a_response(
            an_entry(messageid=1, receptor="09121234567"),
            an_entry(messageid=2, receptor="09351234567"),
        ),
    )
    result = KavenegarSync(API_KEY).send_bulk(
        BulkSmsMessage(receptors=["0912 123 4567", "۰۹۳۵۱۲۳۴۵۶۷"], text=TEXT)
    )

    assert result.message_ids == ("1", "2")
    assert result.cost == 240
    assert stub.last(SEND).form["receptor"] == "09121234567,09351234567"


async def test_send_bulk_async(stub: Stub) -> None:
    stub.reply(SEND, a_response(an_entry(messageid=1), an_entry(messageid=2)))
    result = await KavenegarAsync(API_KEY).send_bulk(
        BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text=TEXT)
    )
    assert result.message_ids == ("1", "2")


def test_send_bulk_pairs_local_ids_by_position(stub: Stub) -> None:
    stub.reply(SEND, a_response(an_entry(), an_entry(messageid=2)))
    KavenegarSync(API_KEY).send_bulk(
        BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text=TEXT, local_ids=["a-1", "a-2"])
    )
    assert stub.last(SEND).form["localid"] == "a-1,a-2"


def test_mismatched_local_ids_are_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="wrong numbers"):
        KavenegarSync(API_KEY).send_bulk(
            BulkSmsMessage(receptors=[RECEPTOR, "09351234567"], text=TEXT, local_ids=["a-1"])
        )
    assert stub.paths == []


def test_an_empty_batch_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="empty recipient list"):
        KavenegarSync(API_KEY).send_bulk(BulkSmsMessage(receptors=[], text=TEXT))


def test_an_oversized_batch_is_refused_before_sending(stub: Stub) -> None:
    """Kavenegar rejects a batch over 200 whole, so none of it goes out. Catching it here means
    the caller learns that from an exception naming the limit rather than from silence."""
    with pytest.raises(ConfigurationError, match="at most 200 recipients"):
        KavenegarSync(API_KEY).send_bulk(BulkSmsMessage(receptors=[RECEPTOR] * 201, text=TEXT))
    assert stub.paths == []


def test_duplicates_are_kept(stub: Stub) -> None:
    """Kavenegar bills per entry. Collapsing duplicates would quietly change what is charged and
    hide the bug in whatever built the list."""
    stub.reply(SEND, a_response(an_entry(), an_entry(messageid=2)))
    KavenegarSync(API_KEY).send_bulk(BulkSmsMessage(receptors=[RECEPTOR, RECEPTOR], text=TEXT))
    assert stub.last(SEND).form["receptor"] == f"{RECEPTOR},{RECEPTOR}"


# ---------------------------------------------------------------------------------------------
# Pattern send
# ---------------------------------------------------------------------------------------------


def test_send_pattern_sync(stub: Stub) -> None:
    """``verify/lookup`` answers with a bare object rather than a one-element array."""
    stub.reply(LOOKUP, {"return": APPROVED, "entries": an_entry(messageid=999)})
    result = KavenegarSync(API_KEY).send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="verify", tokens=["12345"])
    )

    assert result.message_id == "999"
    sent = stub.last(LOOKUP).form
    assert sent == {"receptor": RECEPTOR, "template": "verify", "token": "12345"}


async def test_send_pattern_async(stub: Stub) -> None:
    stub.reply(LOOKUP, {"return": APPROVED, "entries": an_entry(messageid=999)})
    result = await KavenegarAsync(API_KEY).send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="verify", tokens=["12345"])
    )
    assert result.message_id == "999"


def test_positional_tokens_become_token_token2_token3(stub: Stub) -> None:
    stub.reply(LOOKUP, {"return": APPROVED, "entries": an_entry()})
    KavenegarSync(API_KEY).send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="order", tokens=["12345", "b", "c"])
    )
    sent = stub.last(LOOKUP).form
    assert sent["token"] == "12345"
    assert sent["token2"] == "b"
    assert sent["token3"] == "c"


def test_named_tokens_are_passed_through(stub: Stub) -> None:
    stub.reply(LOOKUP, {"return": APPROVED, "entries": an_entry()})
    KavenegarSync(API_KEY).send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="order", tokens={"token10": "علی رضایی"})
    )
    assert stub.last(LOOKUP).form["token10"] == "علی رضایی"


def test_a_space_in_a_plain_token_is_refused(stub: Stub) -> None:
    """The single most common way a pattern send fails, and Kavenegar's own error never says so."""
    with pytest.raises(ConfigurationError, match="whitespace in token2"):
        KavenegarSync(API_KEY).send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="order", tokens=["1", "علی رضایی"])
        )


@pytest.mark.parametrize("slot", ["token10", "token20"])
def test_the_two_slots_that_allow_spaces(stub: Stub, slot: str) -> None:
    stub.reply(LOOKUP, {"return": APPROVED, "entries": an_entry()})
    KavenegarSync(API_KEY).send_pattern(
        PatternMessage(receptor=RECEPTOR, pattern="order", tokens={slot: "a b"})
    )
    assert stub.last(LOOKUP).form[slot] == "a b"


def test_an_overlong_token_is_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="100 characters"):
        KavenegarSync(API_KEY).send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="order", tokens=["x" * 101])
        )


def test_too_many_tokens_are_refused(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="at most 20 tokens"):
        KavenegarSync(API_KEY).send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="order", tokens=["x"] * 21)
        )


def test_a_pattern_send_refuses_a_sender(stub: Stub) -> None:
    """Lookup has no sender parameter; the template owns the line. Dropping it silently would send
    a one-time code from a line nobody expected."""
    with pytest.raises(ConfigurationError, match="no sender parameter"):
        KavenegarSync(API_KEY).send_pattern(
            PatternMessage(receptor=RECEPTOR, pattern="verify", tokens=["1"], sender="10004346")
        )


def test_a_pattern_send_needs_a_template(stub: Stub) -> None:
    with pytest.raises(ConfigurationError, match="needs a template"):
        KavenegarSync(API_KEY).send_pattern(PatternMessage(receptor=RECEPTOR, pattern="  "))


# ---------------------------------------------------------------------------------------------
# Refusals and failures
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (403, "invalid API key"),
        (418, "insufficient credit"),
        (424, "template not found"),
        (412, "invalid sender number"),
    ],
)
def test_a_refusal_raises_with_the_code_and_an_english_reason(
    stub: Stub, status: int, expected: str
) -> None:
    stub.reply(SEND, {"return": {"status": status, "message": "خطا"}}, status=status)
    with pytest.raises(ProviderError) as exc:
        KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))

    assert exc.value.code == status
    assert expected in str(exc.value)
    assert exc.value.raw["return"]["message"] == "خطا"


async def test_a_refusal_raises_on_the_async_engine_too(stub: Stub) -> None:
    stub.reply(SEND, {"return": {"status": 418, "message": "خطا"}}, status=418)
    with pytest.raises(ProviderError) as exc:
        await KavenegarAsync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert exc.value.code == 418


def test_an_unknown_status_still_raises_with_what_kavenegar_said(stub: Stub) -> None:
    """A code not in the table is reported with Kavenegar's own Persian text, not swallowed."""
    stub.reply(SEND, {"return": {"status": 999, "message": "یک خطای تازه"}})
    with pytest.raises(ProviderError) as exc:
        KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert exc.value.code == 999
    assert "یک خطای تازه" in str(exc.value)


def test_an_accepted_call_with_no_entries_raises(stub: Stub) -> None:
    """Nothing was sent, and nothing said so. Returning an empty result would let this pass for a
    successful send everywhere the caller does not count the messages."""
    stub.reply(SEND, {"return": APPROVED, "entries": []})
    with pytest.raises(ProviderError, match="nothing was sent"):
        KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))


def test_a_non_json_body_is_a_network_error(stub: Stub) -> None:
    stub.reply_text(SEND, "<html>502 Bad Gateway</html>", status=502)
    with pytest.raises(NetworkError, match="non-JSON"):
        KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))


async def test_a_non_json_body_is_a_network_error_async(stub: Stub) -> None:
    """``aiohttp`` refuses to decode a body served as ``text/html``; the transport reads the text
    itself so both engines fail the same way."""
    stub.reply_text(SEND, "<html>502 Bad Gateway</html>", status=502)
    with pytest.raises(NetworkError, match="non-JSON"):
        await KavenegarAsync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))


def test_an_empty_api_key_fails_at_construction() -> None:
    with pytest.raises(ConfigurationError, match="api_key"):
        KavenegarSync("   ")


# ---------------------------------------------------------------------------------------------
# The API key must not leak
# ---------------------------------------------------------------------------------------------


def _closed_port() -> int:
    """A port nothing is listening on — bound to find a free one, then released."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    return port


def test_the_api_key_is_scrubbed_from_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``requests`` puts the failing URL in its exception, and Kavenegar's URL holds the key."""
    monkeypatch.setattr(
        kavenegar_helpers,
        "BASE_URL",
        f"http://127.0.0.1:{_closed_port()}/v1/{{api_key}}/{{scope}}/{{method}}.json",
    )
    with pytest.raises(NetworkError) as exc:
        KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert API_KEY not in str(exc.value)


async def test_the_api_key_is_scrubbed_on_the_async_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        kavenegar_helpers,
        "BASE_URL",
        f"http://127.0.0.1:{_closed_port()}/v1/{{api_key}}/{{scope}}/{{method}}.json",
    )
    with pytest.raises(NetworkError) as exc:
        await KavenegarAsync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert API_KEY not in str(exc.value)


def test_the_api_key_is_scrubbed_from_an_undecodable_body(stub: Stub) -> None:
    """A proxy or WAF that echoes the request URL into its error page would otherwise put the key
    straight into the exception text."""
    stub.reply_text(SEND, f"<html>cannot reach /v1/{API_KEY}/sms/send.json</html>", status=502)
    with pytest.raises(NetworkError) as exc:
        KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert API_KEY not in str(exc.value)
    assert "***" in str(exc.value)


def test_the_api_key_is_not_in_the_config_repr() -> None:
    """This object lands in tracebacks and debugger frames."""
    assert API_KEY not in repr(KavenegarSync(API_KEY).config)


# ---------------------------------------------------------------------------------------------
# Registry and protocols
# ---------------------------------------------------------------------------------------------


def test_the_registry_knows_kavenegar() -> None:
    """The full list is asserted once, in ``test_smsir.py``; this only checks it is in there."""
    assert "kavenegar" in available()


def test_both_engines_are_reachable_by_name(stub: Stub) -> None:
    stub.reply(SEND, a_response(an_entry()))
    provider = get_sync_provider("kavenegar", api_key=API_KEY)
    assert provider.send(SmsMessage(receptor=RECEPTOR, text=TEXT)).message_id == "8792343"
    assert isinstance(get_async_provider("kavenegar", api_key=API_KEY), KavenegarAsync)


def test_an_unknown_provider_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="unknown provider"):
        get_sync_provider("nosuchprovider", api_key=API_KEY)


def test_the_classes_satisfy_their_protocols() -> None:
    assert isinstance(KavenegarSync(API_KEY), ISyncSmsProvider)
    assert isinstance(KavenegarAsync(API_KEY), IAsyncSmsProvider)


def test_details_carry_the_return_object(stub: Stub) -> None:
    stub.reply(SEND, a_response(an_entry()))
    result = KavenegarSync(API_KEY).send(SmsMessage(receptor=RECEPTOR, text=TEXT))
    assert isinstance(result.details, KavenegarDetails)
    assert result.details.return_status == 200
    assert result.details.return_message == "تایید شد"
    assert result.details.status_description == "approved"
