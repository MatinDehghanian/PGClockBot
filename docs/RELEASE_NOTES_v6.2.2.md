# Release notes — v6.2.2

## Mini App — security + mobile polish

### Security
- Platform **admin/owner**: ops overview only — **no** buy / renew / wallet commerce
- Buy/renew APIs reject non-commerce personas (`403`)
- Service/QR endpoints require ownership + commerce persona
- Catalog is **platform plans only** (no foreign reseller shop leakage)
- Subscription info uses the service's own token with `auth=False` (no admin JWT)

### UX
- Status badges match panel chips (no heavy circle look)
- Subscription URL text removed from service cards (copy / QR / open remain)
- Orange border on floating bottom nav
- Home shows compact service peeks (full cards only on Services tab)
