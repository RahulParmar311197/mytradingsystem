# Historical market data API

All routes require an API bearer token. A viewer can list instruments, closed candles and data-quality events;
only an operator can import instruments and raw historical candles. Set `MTS_API_VIEWER_TOKEN` and
`MTS_API_OPERATOR_TOKEN` to distinct random values of at least 32 characters. Database migrations through
`0015_replay_playback_runs` contain the required instrument, raw candle, normalized candle and quality tables.

From the repository root after installing the development dependencies and applying migrations:

```bash
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Import one instrument with `POST /api/v1/operator/instruments`:

```json
{"instruments":[{"id":"11111111-1111-4111-8111-111111111111","symbol":"NIFTY 50","exchange":"NSE","segment":"CASH","tick_size":"0.05","lot_size":1}]}
```

Ingest candles with `POST /api/v1/operator/market-data/candles`:

```json
{"source":"authorized-feed","candles":[{"instrument_id":"11111111-1111-4111-8111-111111111111","timestamp":"2026-09-24T09:15:00+05:30","timeframe_seconds":60,"open":"100","high":"101","low":"99","close":"100.5","volume":"1000","source_event_id":"feed-1"}]}
```

The response counts newly inserted raw rows, normalized rows and quality events. A malformed OHLC bar remains
in the raw table and creates an explicit quality event; it does not appear in normalized results. A retry with
the same source event IDs is idempotent. An unknown instrument is rejected before writing the batch.
A source event ID reused with changed candle content returns HTTP 409.
When a different feed supplies a different value for an existing candle identity, the raw event is retained and
`CONFLICTING_CANDLE` appears in quality events; the normalized value is not silently replaced.

Read with `GET /api/v1/instruments/{id}/candles?start=2026-09-24T03:45:00Z&end=2026-09-24T04:00:00Z&as_of=2026-09-24T03:50:00Z&timeframe_seconds=60&aggregate_seconds=300`.
The API returns only closed source candles available by `as_of`. An aggregated candle appears only after its
complete source bucket closes. NSE daily source candles become available at the 15:30 Asia/Kolkata close.
`GET /api/v1/instruments/{id}/quality-events` exposes rejected records and warning events. Lists support
bounded `limit` and `offset`; historical queries span at most 31 days per request.

This API ingests supplied authorized historical data. Broker feed authentication, corporate action adjustments,
large imports, and provider licensing remain separate work.

## NSE session calendar for weekly candles

Apply migration `0016_exchange_sessions`. Operators import reviewed session dates through
`POST /api/v1/operator/calendars/nse/sessions`:

```json
{"source":"owner-reviewed-calendar","published_at":"2026-09-13T00:00:00Z","sessions":[{"exchange":"NSE","session_date":"2026-09-14","opens_at":"2026-09-14T09:15:00+05:30","closes_at":"2026-09-14T15:30:00+05:30","is_trading_day":true}]}
```

Provide one session for every weekday of each requested week, including closed holidays
(`is_trading_day=false`). The source and publication timestamp must reflect evidence available at the
requested `as_of` time; missing or incomplete calendars cause weekly aggregation to fail closed. Existing
calendar entries are immutable through this API: a conflicting revision returns HTTP 409 for manual review.
A successful import is audited. Authenticated users can inspect a bounded date range using
`GET /api/v1/calendars/nse/sessions?start=2026-09-14&end=2026-09-18`.
For weekly candle reads set `timeframe_seconds=86400` and `aggregate_seconds=604800`.

The API does not fetch an official holiday calendar; the operator must supply and verify dates, including special
sessions. Daily and intraday candle aggregation still assumes the standard 09:15–15:30 IST session. Calendar
versioning, revisions and special-session intraday buckets require further implementation.
