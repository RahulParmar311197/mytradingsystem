# Broker API assumptions

The order adapters were checked on 2026-09-19 against the official Upstox place/cancel/order-details pages and the
official Dhan v2 order API page. Upstox placement uses `POST https://api-hft.upstox.com/v2/order/place`, cancellation
uses `DELETE https://api-hft.upstox.com/v2/order/cancel`, and details use
`GET https://api.upstox.com/v2/order/details`. Dhan uses `https://api.dhan.co/v2/orders` and the documented
`/{order-id}` resource. Broker documentation can change; these mappings require contract review before release.

References:

- <https://upstox.com/developer/api-documentation/place-order/>
- <https://upstox.com/developer/api-documentation/cancel-order/>
- <https://upstox.com/developer/api-documentation/get-order-details/>
- <https://dhanhq.co/docs/v2/orders/>

Credentials are accepted only as constructor values intended to originate from environment/secret providers. They
are sent in Upstox `Authorization: Bearer` or Dhan `access-token` headers and are never included in adapter errors.
Required deployment variables are `MTS_UPSTOX_ACCESS_TOKEN`, `MTS_DHAN_CLIENT_ID`, and `MTS_DHAN_ACCESS_TOKEN`.

Every placement request requires the matching independent `RiskDecision`, with an `APPROVED` or `RESIZED` outcome
and an approved quantity exactly equal to the broker request. Validation occurs before network I/O. Placement is
never automatically retried; a timeout or uncertain response must enter execution reconciliation before any further
action. Client correlation/tag IDs are always supplied. Get/cancel calls are currently thin mappings without retry.

Only place, details, and cancel are implemented in this slice. Token renewal, instruments, quotes, historical/live
data, modification, trades, positions, holdings, funds/margins, and order streams remain incomplete. No live broker
test runs by default, no credential is committed, and live trading remains disabled by configuration.
