# sms-providers-sdk

A unified Python SDK for Iranian SMS providers, with one API surface and two interchangeable engines: **sync** and **async**.

Every provider ships `<Name>Sync` and `<Name>Async` with the same three methods — `send`, `send_bulk`, `send_pattern` — taking and returning the same types. Moving a call site between engines is adding or removing `await`, never a rewrite.

> **Status: early development.** Kavenegar, SMS.ir and Melipayamak are implemented and tested. Expect breaking changes before `1.0`.

## Why

Every provider invents its own request shape, its own status codes, and its own name for "template". This SDK normalises them, so adding or switching a provider is a one-line change in your application.

- **One API, every provider** — the same three calls regardless of who is behind them.
- **Two engines, same surface** — identical method names, arguments and return types on both.
- **A send that did not happen raises** — no `success` flag to forget to check.
- **Typed end to end** — dataclasses everywhere, `py.typed` shipped, clean under `mypy --strict`.
- **Credentials do not leak** — two of the three providers put the API key in the URL, so it is scrubbed out of every error message before it can reach a log, and no config object carries a key in its `repr`.
- **Nothing is flattened away** — each provider also returns its own record with everything *it* reports.

## Installation

```bash
pip install sms-providers-sdk
```

Requires Python 3.10 or newer. No extras and no optional dependencies: `aiohttp` drives the async engine, `requests` the sync one.

## Quick start

### Sync engine — scripts, Django, Celery workers

```python
from sms_providers_sdk import BulkSmsMessage, KavenegarSync, PatternMessage, SmsMessage

sms = KavenegarSync(api_key="your-api-key")  # sender="10004346" to pin a line

# One message, one recipient.
result = sms.send(SmsMessage(receptor="09121234567", text="سفارش شما ثبت شد."))
store(order, message_id=result.message_id)

# The same message to many recipients, in one call.
result = sms.send_bulk(
    BulkSmsMessage(
        receptors=["09121234567", "09351234567"],
        text="فروشگاه فردا تعطیل است.",
        extra={"hide": 1},  # keep recipients from seeing each other
    )
)
print(len(result), result.cost)

# A template registered in the provider's panel.
result = sms.send_pattern(
    PatternMessage(receptor="09121234567", pattern="verify", tokens=["12345"])
)
```

### Async engine — FastAPI, aiohttp, anything on asyncio

The same calls, awaited:

```python
from sms_providers_sdk import KavenegarAsync, SmsMessage

sms = KavenegarAsync(api_key="your-api-key")
result = await sms.send(SmsMessage(receptor="09121234567", text="سلام"))
```

`send_bulk` is one text to many numbers. When the texts differ there is no single call for it — `asyncio.gather` over `send` is what keeps that from being N round-trips in series.

### Switching provider

The same three calls, a different class:

```python
from sms_providers_sdk import SmsIrSync, SmsMessage

sms = SmsIrSync(api_key="your-api-key", line_number="30007487")  # SMS.ir requires a line
result = sms.send(SmsMessage(receptor="09121234567", text="سفارش شما ثبت شد."))
```

The inputs and outputs are identical. Where the providers genuinely disagree — the sending line, batch caps, how a template is identified — the SDK enforces each one's rules before the request goes out; see [Where the providers differ](#where-the-providers-differ).

## The API

### What goes in

| | Fields |
| --- | --- |
| `SmsMessage` | `receptor`, `text`, `sender=""`, `send_at=None`, `local_id=""`, `extra={}` |
| `BulkSmsMessage` | `receptors`, `text`, `sender=""`, `send_at=None`, `local_ids=()`, `extra={}` |
| `PatternMessage` | `receptor`, `pattern`, `tokens=()`, `sender=""`, `extra={}` |

`send_at` is a Unix timestamp. `local_id` is your own reference, echoed back — worth setting on anything that matters, because it is what makes a retried send idempotent at the provider and what lets a delivery report find your record.

`extra` is merged into the outgoing payload verbatim. Providers differ in the long tail — Kavenegar's `hide`, `type`, `tag` — and forcing those into the shared shape would make it the union of every provider rather than the part that is common.

### What comes back

`SmsResult` describes what the provider accepted:

```python
result.message_id  # the first message's id — what you store after a single send
result.message_ids  # every id, for a bulk send
result.receptors  # every recipient accepted, in the same order
result.cost  # Decimal — the whole call, in the provider's own unit
result.details  # the provider's own call-level record, typed
result.raw  # its decoded response, untouched
len(result)  # recipients accepted
for entry in result:  # one SentMessage each
    entry.receptor, entry.status, entry.status_text, entry.sender, entry.cost, entry.message_id
```

`SentMessage.status` is the state **at send time** — queued, or scheduled. It is not a delivery confirmation; delivery is reported minutes later, through a status call or a webhook, against these ids.

Cost is a `Decimal`, because these units are not all integers: Kavenegar bills in Rial, SMS.ir in credits at `1.0` a message. It compares equal to the matching `int`, so `result.cost == 120` reads the same as it would have. Melipayamak reports no cost on either send endpoint, so it is always `None` there — credit is a separate call.

`result.cost` is a field rather than a sum over the entries, because the providers disagree about where the number lives — Kavenegar prices each message, SMS.ir prices the batch and says nothing per recipient. Deriving one from the other would have meant inventing a per-message figure by dividing, so each provider fills in whichever one it was actually told. For SMS.ir bulk sends, `entry.cost` is therefore `None` and `result.cost` carries the total.

### Recipient numbers are normalised

`09121234567`, `0912 123 4567`, `+989121234567`, `00989121234567`, `۰۹۱۲۱۲۳۴۵۶۷` and `٠٩١٢١٢٣٤٥٦٧` all go out as `09121234567`. Persian and Arabic-Indic digits look identical to ASCII in a terminal, so the rejection they cause is one of the harder ones to see: the number in the log reads correctly and the provider still says 411.

Short codes are left alone. `98…` is only rewritten for a 12-digit mobile, because a real line beginning with those digits must not be turned into a phone number.

## Failures

Sending is a request-path operation: there is no callback and nothing to reconcile later, so a send that did not happen **raises**. That is why `SmsResult` has no `success` flag — a boolean that is always `True` is a check people write and never exercise.

| Exception | Means | What to do |
| --- | --- | --- |
| `ConfigurationError` | The message could not be built, or the provider is misconfigured. Nothing was sent. | Fix the input; retrying changes nothing. |
| `ProviderError` | The provider was reached and refused. Nothing was sent. | Branch on `.code` — the provider's own number. It is `None` for Melipayamak, which reports failures as sentences rather than codes. |
| `NetworkError` | Unreachable, timed out, or an undecodable answer. | Ambiguous: the message may or may not have gone. Retry with the same `local_id` so the provider deduplicates. |
| `UnsupportedOperation` | This provider does not offer the operation. | — |

All four derive from `SmsError`.

```python
from sms_providers_sdk import NetworkError, ProviderError, SmsMessage

try:
    result = sms.send(SmsMessage(receptor="09121234567", text="سلام"))
except ProviderError as exc:
    if exc.code == 418:  # insufficient credit — an operator's problem
        alert_ops(exc)
    elif exc.code == 451:  # rate limited — worth retrying
        retry_later()
except NetworkError:
    retry_with_same_local_id()
```

Validation happens before the request goes out, so an empty message, a malformed number, an oversized batch or a token with a space in it fails with a sentence rather than with a numeric provider code.

## Kavenegar

```python
KavenegarSync(api_key, *, sender="", timeout=15.0)
KavenegarAsync(api_key, *, sender="", timeout=15.0)
```

`sender` is the line every message from this instance goes out on, and a `sender` on an individual `SmsMessage` overrides it. One of the two is **required** for `send` and `send_bulk`.

Kavenegar's API documents `sender` as optional, falling back to the account's default line — but that default is unset unless someone configured it, and the fallback fails with 412 "invalid sender number", naming a value you never supplied. So the SDK requires a line up front and raises `ConfigurationError` instead. (Kavenegar's own SDK hits the same 412; this is an account setting, not a client difference.) `send_pattern` is exempt: `verify/lookup` has no sender parameter, because the line belongs to the template.

| Method | Endpoint |
| --- | --- |
| `send` | `sms/send` |
| `send_bulk` | `sms/send`, recipients comma-separated |
| `send_pattern` | `verify/lookup` |

Three things worth knowing, all of which the SDK checks for you:

- **200 recipients per bulk call.** Kavenegar rejects an oversized batch *whole* — nothing goes out — so `send_bulk` refuses it up front rather than letting the send disappear. Chunk longer lists yourself.
- **No spaces in pattern tokens**, except `token10` and `token20`. This is the single most common way a template send fails, and Kavenegar's own error never mentions spaces. Pass a value with a space as `tokens={"token10": "علی رضایی"}`, or replace the space with a ZWNJ.
- **No sender on a pattern send.** `verify/lookup` has no sender parameter: the line belongs to the template, fixed when it was approved. Passing one is refused rather than dropped silently.

A positional `tokens` sequence fills `token`, `token2` … `token20` in order. A mapping is passed through under its own keys.

`result.details` is a `KavenegarDetails` carrying the `return` object: `return_status` (Kavenegar's numeric code), `return_message` (its own Persian text, verbatim), and `status_description` (the same status in English, so a log line in a service with no Persian in it still says what happened).

**The API key is a URL path segment**, which means both HTTP clients put it in the exceptions they raise, and those go straight into logs and bug reports. Every error message from this SDK is scrubbed on the way out, and `KavenegarConfig` keeps the key out of its `repr` — it lands in tracebacks and debugger frames.

There is no sandbox. Every send is a real, billed message.

## SMS.ir

```python
SmsIrSync(api_key, *, line_number="", timeout=15.0)
SmsIrAsync(api_key, *, line_number="", timeout=15.0)
```

`line_number` is the default sending line. Unlike Kavenegar there is **no account-level default to fall back on**, so it is either set here or carried on every message as `sender` — and the SDK says so up front, because SMS.ir answers a missing line with a bare `101` that reads identically to a mistyped or unowned one.

| Method | Endpoint |
| --- | --- |
| `send` | `POST /v1/send/bulk` with a one-element `mobiles` list |
| `send_bulk` | `POST /v1/send/bulk` |
| `send_pattern` | `POST /v1/send/verify` |

SMS.ir has no dedicated single-send endpoint for free-form text — the only alternative is a legacy `GET /send` that authenticates with a username and password instead of the API key, so `send` is the bulk call with one number.

Four things worth knowing, all of which the SDK checks for you:

- **100 recipients per bulk call**, half Kavenegar's. Rejected whole when exceeded, so `send_bulk` refuses it up front.
- **Templates are numeric ids**, not names: `pattern="100000"`. Passing Kavenegar's template *name* is the obvious mistake when switching providers, so it is refused with a sentence.
- **Template parameters are named, not positional.** SMS.ir placeholders are `#NAME#` and the API matches on the name, so `tokens=["12345"]` has nothing to map onto and is refused rather than guessed at. Use `tokens={"CODE": "12345"}`. Values cap at **25 characters** — short enough that a full name overruns it.
- **No line on a pattern send.** Like Kavenegar's lookup, `send/verify` has no line parameter: the template owns it.

`local_ids` is refused on a bulk send. SMS.ir has no client-supplied message reference — it assigns a `packId` instead, which comes back on `result.details.pack_id` and is the only handle that can cancel a scheduled send (`DELETE /send/scheduled/{packId}`).

`sendDateTime` must be between an hour and a year ahead. That one is documented but *not* enforced, because checking it needs a clock and a client a few minutes out of sync would then have legitimate sends refused locally — a worse failure than the provider's own, which at least reflects the provider's clock.

`result.details` is an `SmsIrDetails`: `status`, `status_message` (SMS.ir's Persian text, verbatim), `status_description` (the same in English) and `pack_id`.

The API key travels in an `X-API-KEY` header, so it never reaches the URL. `SmsIrConfig` still keeps it out of its `repr`.

## Melipayamak

```python
MelipayamakSync(api_key, *, sender="", timeout=15.0)
MelipayamakAsync(api_key, *, sender="", timeout=15.0)
```

This wraps the **console** API (`console.melipayamak.com`), not the older `rest.payamak-panel.com` one that Melipayamak's own PHP/Python/Node samples still use. The console API is the one that takes an API key, accepts a real recipients *array* for a group send, and returns one id per recipient — the legacy API authenticates with a username and password, takes recipients as a comma-joined string, and returns a single id for the whole batch.

`sender` is the default sending line, required by both free-form sends and with no server-side default.

| Method | Endpoint |
| --- | --- |
| `send` | `POST /api/send/simple/{apikey}` |
| `send_bulk` | `POST /api/send/advanced/{apikey}` |
| `send_pattern` | `POST /api/send/shared/{apikey}` |

Things worth knowing:

- **Success is the id being present, not a status value.** Melipayamak's `status` field is documented only as `"شرح خطا در صورت بروز"` — *description of the error, if one occurs*. A refusal answers HTTP 400 with `{"status": "کلید کنسول معتبر نیست"}` and no `recId` key at all. So nothing here compares `status` against a success value; the id decides.
- **No numeric error codes.** Kavenegar has 418, SMS.ir has 102, Melipayamak has a Persian sentence. `ProviderError.code` is therefore `None` for this provider and the message carries the meaning. It is left `None` deliberately rather than filled with the HTTP status, which would give you something to branch on that Melipayamak never promised to keep stable.
- **Two failure shapes.** Beyond the one above, a malformed request never reaches Melipayamak's code: ASP.NET Core's model binder rejects it first with RFC 7807 ProblemDetails, where `status` is the **integer** `400` and the useful part is `title` plus `errors`. Reading that field as text would report the failure as `"400"`, so the two shapes are told apart and the validation errors are surfaced.
- **`send_at` is refused, not dropped.** Scheduling is a separate `send/schedule` method this SDK does not wrap. Silently ignoring `send_at` would send the message *immediately* — the one failure a caller scheduling a message would never think to check for.
- **Template arguments are positional**, the mirror of SMS.ir: `args` is a bare array filled in order, so a mapping's keys would be dropped and its values sent in an order the caller never chose. `bodyId` is a 32-bit integer.
- **No recipient cap is enforced.** Melipayamak documents none for `send/advanced`, and inventing one would refuse batches the account is entitled to send. The other two are capped here only because their own documentation states the number.
- `local_id` / `local_ids` are refused — there is no client-supplied reference, only the `recId` Melipayamak assigns.

An unmatched method or path does **not** 404: Melipayamak answers HTTP 200 with the console's own Angular page. That surfaces as a `NetworkError` naming the non-JSON body, because the transport decides on the body rather than on the status line.

Melipayamak's ids are 64-bit and its own examples already exceed `int32`. Python's integers are arbitrary-precision so nothing is lost — a JavaScript client needs a bigint library to avoid corrupting ids past 2^53 — but they are exposed as strings so they survive being re-serialised.

### Where the providers differ

| | Kavenegar | SMS.ir | Melipayamak |
| --- | --- | --- | --- |
| Auth | key in URL path | `X-API-KEY` header | key in URL path |
| Wire format | form-encoded in, JSON out | JSON both ways | JSON both ways |
| Success signal | `return.status == 200` | `status == 1` | an id is present |
| Error codes | numeric (418, 424 …) | numeric (102, 113 …) | **none** — Persian text |
| Sending line | optional, account default | **required** | **required** |
| Bulk cap | 200 | 100 | undocumented, uncapped |
| Bulk recipients | comma-joined string | JSON array | JSON array |
| Template id | a name (`"verify"`) | numeric (`"100000"`) | numeric (`"524"`) |
| Template params | positional **or** named | **named only** (`#NAME#`, 25 chars) | **positional only** |
| Cost | per message, Rial | per call, credits | not reported |
| Scheduling | `send_at` | `send_at` | refused (separate endpoint) |
| Client-side id | `local_id` | none — `packId` | none — `recId` |

All three are reached through the same three calls, and everything above is checked before the request goes out.

**There is no portable `tokens` form.** SMS.ir accepts named parameters only, Melipayamak positional only; they are genuine opposites, and Kavenegar happens to take either. If you switch providers, the template call is the one place you have to change — which is honest, since the templates themselves live in each provider's own panel anyway.

## Choosing a provider at runtime

```python
from sms_providers_sdk import available, get_async_provider, get_sync_provider

available()  # ('kavenegar', 'melipayamak', 'smsir')
sms = get_sync_provider("kavenegar", api_key="…")  # ISyncSmsProvider
sms = get_async_provider("smsir", api_key="…", line_number="30007487")  # IAsyncSmsProvider
```

The registry holds **classes, not instances**. One instance carries one account's credentials, so build one per account rather than caching a provider globally. An unknown name raises `ConfigurationError` listing what is available.

`ISyncSmsProvider` and `IAsyncSmsProvider` are `typing.Protocol`, so providers satisfy them structurally — nothing inherits from them, and your own provider does not have to either.

## Layout

Each provider package holds the same five things:

```
sms_providers_sdk/providers/<name>/
├── constants.py     endpoints and the fixed values its protocol defines
├── data.py          credentials and the provider's own result records — dataclasses only
├── helpers.py       the pure functions that build payloads and read responses
├── sync_engine.py   a thin shell over helpers
└── async_engine.py  the same shell, awaited
```

That split is why the two engines cannot drift apart: every decision about what a provider was asked and what it answered lives in `helpers.py` and is shared, so only the transport call differs.

`common/http.py` carries both wire formats — `post_form`/`apost_form` and `post_json`/`apost_json` — so a provider module never touches an HTTP client directly. That is also what keeps credential scrubbing in one place instead of in each provider.

## Development

```bash
uv sync --all-groups
uv run pytest             # the suite
uv run mypy               # strict
uv run pyright            # strict, and a second opinion
uv run ruff check .
uv run ruff format --check .
```

All five are clean, and the two type checkers are both worth running: they disagree about what `isinstance` narrowing proves on a value that came out of `json.loads`, so a body of JSON-parsing code that satisfies one can still be full of implicit `Any` under the other. That is what `as_mapping` and `as_sequence` in `common/utils.py` exist for.

`[tool.pyright]` sets `venvPath`/`venv` so the checker resolves against `.venv`. Without it every third-party import reads as unresolved and each one cascades into dozens of "type is unknown" errors. In VS Code, the selected interpreter wins over that setting — point it at `./.venv/bin/python` (**Python: Select Interpreter**) and install the package itself with `pip install -e .`, or Pylance will report the same thing the CLI would.

The tests run against a **real HTTP server** on a real port — there is no mocking library anywhere in the suite. An in-process mock will accept a request no server would: an unencoded body, a field the provider dispatches on quietly missing, an `int` where `aiohttp` demands a string. The server sees exactly what the SDK put on the wire, and both engines are held to the same bytes.

Every test that exercises a sync class has an async twin with the same fixtures. A change that breaks one engine and not the other shows up there rather than in production.

## License

MIT
