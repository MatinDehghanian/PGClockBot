# Service and customer isolation between shops

Status: design (phase 0). No behavior changes in this document's pull request.

## 1. Problem

A person is one `bot_users` row (`telegram_id` is unique). The row carries one shop (`reseller_id`), assigned the first time the person opens a shop bot (`get_or_create_user`, "first-touch attribution"). Almost everything that decides what a shop, a customer or the platform may see is keyed on that user-level shop:

- the web panel and the shop bot list customers with `BotUser.reseller_id == shop`, then load their services by `bot_user_id` only;
- customer lists, details, subscription links, QR codes and deletes in the bots and the Mini App check only `bot_user_id`;
- notifications, campaigns, rewards and the panel client choice read `user.reseller_id`.

Consequence: a platform customer who opens a shop bot is moved to that shop. The shop's staff then see, renew, extend and delete the platform-sold services, the platform loses the customer from its own list, and both bots show the same services. Several Owner-side routes also reach into shop data without a scope check (listed in section 8).

The features that already compare the service's shop with the current bot (renew, add-on packs, cancellation, automation) use `service_shop_id` (`app/services/service_automation.py`): the shop of the fulfilling order, falling back to the user's attribution. That helper is the right idea but is not applied everywhere and is wrong for services without an order.

## 2. Invariants

1. A service belongs to exactly one shop (or the platform), decided when it is created and never inferred from who the customer is today.
2. A bot, panel session or Mini App for shop S may read or change a service only if the service's shop is S. The platform bot and the Owner web panel are the platform shop (`NULL`); the Owner reads shop data only through the web panel and only where this document allows it (section 6).
3. A person can be a customer of several shops. Their services, tickets, orders, wallets and notifications stay in the shop that produced them.
4. A user-level action (block, role, delete, wallet adjustment, direct message) is allowed only for the shop the user is attributed to; it never reaches the services of another shop.
5. Every check happens where the mutation happens, on the loaded record, not only on the list that led to it.

## 3. Decision: shop on the service

Add `user_services.shop_id` (nullable `ForeignKey("bot_users.id")`, indexed). `NULL` means platform, the same convention as `orders.reseller_id`.

Rejected alternatives:

- **One `bot_users` row per (telegram_id, shop).** Cleanest model, but `telegram_id` is unique and referenced by auth, referral, wallet and admin identity. Splitting rows is a data migration with no safe rollback.
- **Reuse `user_services.owner_principal_id`.** It is the Phase 1E principal dimension and is itself backfilled from the sticky `BotUser.reseller_id` (`resource_principal.py`), so it carries the same error and its `NULL` means "unknown", not "platform".
- **Keep deriving the shop from the order remark.** Works only for `order:N`; imported, linked and manually created services have no order.

Where the shop is known at creation (all three creation sites):

| Site | Shop source |
| --- | --- |
| `orders.py` delivery (`remark = order:N`) | `order.reseller_id` |
| `bot_user_admin.py` manual provisioning | the shop of the acting scope (`shop_rid`) |
| `service_import.py` import | the import `shop_id` |

## 4. Backfill and its limit

Migration `NNNN_service_shop_id` (idempotent, SQLite and PostgreSQL, keyset batches, `downgrade` drops the column and index):

1. `remark = 'order:N'` and the order belongs to the same user: `shop_id = order.reseller_id`.
2. Everything else (`imported`, `linked`, `manual:*`, malformed remark): `shop_id = bot_users.reseller_id` of the owner. This is the only available signal.

Known limit: for category 2 the result is wrong when the user was re-attributed after the service existed (a platform import that was later re-attributed). It cannot be detected from the data. The migration does not guess further; a read-only report lists users who have a service of category 2 and an order or service of another shop, so the owner can review them. No automatic reassignment.

## 5. One check, one helper

`app/services/service_scope.py` (new module, no Telegram or FastAPI types):

- `service_in_shop(service, shop_id) -> bool` and `assert_service_in_shop(service, shop_id)` (raises the domain `ValueError` with the existing Persian message).
- `shop_services_clause(shop_id)` for queries (`UserService.shop_id IS NULL` or `== shop_id`).
- `shop_member_clause(shop_id)`: a customer belongs to a shop if `BotUser.reseller_id == shop_id` or the customer has a service or an order of that shop. The platform clause is the mirror (unattributed, or has a platform service or order). This keeps a customer visible to the platform after attribution and visible to a shop that never attributed them.
- `current_shop_reseller_id()` stays the single source of "which bot is this".

`service_shop_id` becomes a thin reader of the column. Call sites to convert, grouped by pull request in section 7.

## 6. Roles

| Actor | Rule |
| --- | --- |
| Customer in a shop bot or Mini App | Sees and manages only services with that shop. The platform Mini App shows only platform services and uses the platform catalog and purse. |
| Shop owner and shop staff (bot and web panel) | Customers by `shop_member_clause`; services only by `shop_services_clause`. User-level actions only for attributed customers. |
| Platform admin in the platform bot | Platform services only. Shop customers and shop services are denied. |
| Owner in the web panel | Own scope (`/users`, orders, payments) is the platform. Owner may still use `/pg/users` for the whole panel, but a delete there requires a reason, is logged, and detaches only through the same scoped helper. Owner may not reach shop customers or shop wallets through `delete-user`, broadcast or payment approval. |
| Resellers' own personal account | Treated as a customer of the platform. The shop panel never lists it. From a shop bot it sees only services of that shop. |
| L1 and L2 principals | Unchanged; scope stays by their linked shop. |

## 7. Pull requests

Pull request A (no migration, no change to what a customer sees):

- scope `POST /resellers/{id}/delete-user`; add `reseller_id IS NULL` to the broadcast audience; reject shop wallet top-up approval by the Owner (single and bulk);
- ticket visibility by `Ticket.reseller_id`; close the fail-open in bulk ticket close;
- `order.reseller_id == current shop` in the `pay:*` handlers;
- stop first-touch re-attribution for a user who already has a service or order;
- until the column exists, `assert_service_in_shop` is built on `service_shop_id` and applied to the panel and bot-admin service operations (`get_owned_service`, quick renew, extend, delete) and to the panel client choice, so a failed lookup is never treated as "already absent".

Pull request B (migration and behavior change):

- the column, backfill and report;
- `service_scope.py` and its use in customer lists and details, link and QR, delete, Mini App, loyalty redemption and wheel;
- notification bot and panel client chosen from the service or order shop;
- campaign audience and scheduler fallback through the helper;
- point balances per shop are tracked as a follow-up, not part of B.

## 7a. Behavior change for customers

A customer of two shops sees two separate lists. A service opened from the wrong bot says it is managed from its own shop's bot (the wording already used by renewals and cancellation). Support should be told before B ships.

## 8. Findings this design closes

Owner side: `delete-user` without scope; broadcast to every shop; wallet top-up approval for another shop's wallet; whole-panel PG views without a logged reason.
Shop and bot side: service list, details, links, delete and operations by user-level shop only; tickets of re-attributed users; payment buttons without the order's shop; notifications, campaigns and rewards keyed on user attribution.

## 9. Tests

For each converted path: a second shop and a second customer cannot read or change the record; a customer with services in two shops sees only the current shop's; a platform customer opening a shop bot keeps their services and is not attributed; an Owner POST for a shop's customer or wallet is refused; a missing or 404 panel answer never deletes a local row. Security and isolation tests go in `scripts/security_test_manifest.txt`. The migration test upgrades, upgrades twice and downgrades, with order-based, imported and malformed-remark rows.

## 10. Open items

- Whether a 404 from the panel client can happen for a live panel user owned by another admin (not verified; the delete path is hardened regardless).
- Point balances per shop.
- The Owner's `/pg/users` design stays; only its logging and reason requirement change.
