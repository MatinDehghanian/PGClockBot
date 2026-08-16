# Release notes — v6.2.3

## Mini App — full security harden

- Blocked users rejected on all Mini App APIs (`403`)
- Force-join enforced on buy/renew for `user` persona (parity with bot)
- `/api/mini/service/{id}` returns allowlisted summary only (no raw PG `info`)
- `pay_with_wallet` fails closed if `order.user_id != payer.id`
- HTTP 500 on buy/renew no longer echoes internal exception text
- Expanded Mini App security audit tests + repaired initData source test
