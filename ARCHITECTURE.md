# Architecture

## Current request paths

| Entry point | Services | Storage and response |
| --- | --- | --- |
| Next.js directory, stock details and chart | FastAPI stocks router, security master, provider manager, indicator engine | SQLite historical sessions and security identities. Chart ranges are sliced after full-history calculations. |
| All-stock plans | StockPlansService, technical rating, trade plan and breakout services | Cached EOD series. An explicit refresh can call a historical provider. |
| Manual live analysis | LiveDecisionEngine, RiskManager, OwnerAddOnAdvisor, market depth and corporate events | The user supplies current price and optional holdings. The current_price_source and executable_quote_verified response fields identify the price as manual. |
| Manual EOD correction | live-analysis/manual-eod, candle validator and correction journal | Only the expected completed session is accepted. The market row and before/after journal commit together. Repeating an identical edit creates no extra journal record. |
| Hosted owner access | Caddy HTTPS and owner credentials, then private loopback services | Same-origin API route, no stored brokerage credentials, no authenticated response caching. |

Phase 1 continues to use a single owner and one backend writer process. A valid EOD series may support analysis. It cannot establish an executable intraday price. Paper accounts, proposals, and real holdings require separate models and authorization before any such routes are exposed.

## SQLite lifecycle

The tracked market snapshot remains available for old installations and recovery. First startup uses SQLite online backup, integrity_check and an atomic create-if-absent operation to create a private writable copy. This requires a local filesystem with hard-link support. WAL and rollback files, runtime stores and backups are ignored. Private database paths belong in the process environment. Alembic versions the additive correction journal; existing market tables and the BIOC archival migration retain their startup behavior. PostgreSQL requires a driver, a tested data migration, and integration tests before use in production.

## Market data and future workers

Accepted EOD bars must identify the requested ticker and a valid completed session. HLCV and open must be finite, volume must be present, and explicit currency/exchange must match EGP/EGX. Records with conflicting values for the same date are excluded within a provider response. Large price discontinuities require further checks. The source code currently cannot prove independence of vendors behind every fallback. Corporate-action adjustment policy, full halt coverage, special sessions, live entitlements and an intraday timestamp policy are still needed.

A future dedicated scanner should persist scan windows, leases and notification idempotency keys. An API-process timer would duplicate work across workers. APScheduler in one external process with a DB lease is the initial candidate for SQLite. Evaluate Celery with Redis when independent queues, retries and load require it. The PWA must never be responsible for running market scans. Phases 2–9 are detailed in IMPLEMENTATION_PLAN.md.

## Read-only Thndr integration

The single-owner gateway overwrites the integration authentication header after authenticating the browser. FastAPI compares that value to its server-side secret. OAuth state is single-use, expires after ten minutes and is bound to a secure HttpOnly browser cookie and a server-side S256 verifier. The authorization server and resource have explicit trusted origins. The backend requests only `thndr:read`, and the official SDK discovers granted MCP tools before use. A separate allowlist constrains those grants to the reads used by the app.

Credentials and the normalized portfolio snapshot are encrypted together. A local file lock serializes callback, refresh, sync and revocation operations. A refresh token rotation is persisted before further calls. A limited read cache is checked against current authorization and tool discovery before serving. Local disconnect clears the private snapshot and blocks access even if upstream revocation needs a later retry.

Quotes retain separate source and retrieval times, instrument identity, provider, currency, venue and session state. Only a fresh quote for a verified instrument from an explicitly entitled real-time provider during an open session can qualify as `REALTIME_VERIFIED`. Thndr is outside that real-time allowlist. No order proposal route is added by this phase.

## Phase 3 · AI analysis trust boundary

The owner-only analysis endpoints load validated completed sessions, reuse EGX26 and the strategy engines, and check broker quotes against the security registry again. An EOD price includes the actual session date. An unavailable source timestamp stays empty. Thndr values that lack a valid quote may be reviewed alongside explicitly dated historical references. A delayed or manual price cannot authorize an order. Manual position sizing continues to use the existing 1.5% planned risk and 20% stock-allocation caps. Owner add-on sizing uses remaining cash, risk and allocation.

The only OpenAI input is a fixed-vocabulary description of evidence, market freshness, and the conditional position action. Company text, event text, URLs, tickers, identifiers, holdings, balances and broker tokens do not cross that boundary. The response can select and order only available evidence codes. The backend renders their Egyptian Arabic wording from controlled templates. Unknown codes, extra fields, refusals, or upstream failure preserve the server's deterministic result.

The protected backend has a persistent SQLite usage ledger. It atomically reserves spend, applies cadence and global rate limits, deduplicates requests, and stores private cache entries keyed by an owner-scoped HMAC of market and portfolio context, model, prompt, schema and strategy versions. The ledger stores no raw portfolio payload. The HTTP transport has no brokerage tools. Ranking uses technical score, trend, turnover proxy, reward relative to risk, proximity, freshness, known exposure and a penalty for missing fundamentals.

## Phase 4 · Owner risk policy and dated screening

The additive migration creates an owner policy record and date-keyed screening evidence by ISIN. Portfolio review inputs are request-scoped. The protected risk endpoint selects manual data or reads the authorized Thndr adapter. Exposures, costs, gaps and sizing use Decimal. Whole-share capacity is the floor of the tightest cash, exposure, per-trade and portfolio-risk limit. Pending buys consume projected capacity and available cash. An absent necessary input or a triggered stop blocks new size calculations. Settlement data is explicit. Adjusted historical equity supports daily and drawdown gates without deriving a history from the broker snapshot.

The optional Islamic policy is enforced in the legacy live analysis, AI analysis, opportunity selection and portfolio sizing. It checks owner-reviewed activity and four ratios from documented EGX methodology. Missing or expired evidence yields UNVERIFIED. Evidence recorded by date remains available and ticker changes cannot relabel a different ISIN. Broker/model paths cannot write screening evidence or change risk policy. These gates run before rendering or model interpretation. The emergency switch, screening, and financial risk checks all leave existing positions visible so that holding and exit scenarios can still be reviewed.

## Phase 5 worker and notifications

FastAPI owns authenticated settings, manual enqueue, result/history and notification state. A standalone Python supervisor owns the scheduler and leases. An expiring job token fences result publication. SQLite immediate writer transactions serialize claims and configuration changes across local processes. The supervisor renews leases, persists its heartbeat and terminates a child at the wall-clock deadline. The child uses a bounded local evaluator pool. The lease is rechecked in the transaction that writes one scan, stable observations, alerts and outbox rows. Jobs recover after crashes and retry bounded compute failures with backoff. No supervisor needs the frontend or a FastAPI process.

The scanner uses the same validated candle cache and technical calculation as existing analysis. Retrieved brokerage observations use a separate field and source. Monitoring never fetches new prices from the broker or public provider adapters. Thndr mode only verifies the authorized grant on the existing integration, and checks local grant state again during publication and reads. Latest validated candle inputs, source context, policy, Sharia classification and strategy/version contribute to the snapshot digest. EOD opportunities are general analysis unless the selected portfolio passes the separate risk sizing review. Current policy, session, identity and screening are re-evaluated before publication. The dashboard suppresses expired and newly blocked entry states while keeping archived evidence.

SQLite provides persistence and atomicity without a second scheduler store. APScheduler would still need shared job claims, fencing and an atomic result/outbox transaction. Celery and RQ require a broker or additional managed infrastructure. Cron cannot track private owner settings, file-local leases or manual requests itself. Phase 5 uses the existing single-host SQLite runtime and standard-library supervisor, so dependency manifests are unchanged. Multi-host scheduling would require a different coordination design.

In-app delivery is committed with the alert. An external adapter interface supports leased attempts and backoff with a limited payload. No external destination is registered. A future provider may receive a duplicate if a worker dies after sending and before recording success. Publish, review-route and notification permissions remain behind the private Caddy gateway.
