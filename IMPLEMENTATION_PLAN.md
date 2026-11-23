# AI trading assistant implementation plan

## Phase 0 audit, 24 November 2026

Base commit `46672ed80e954fba6e04007381cc3e333a7abadd` on main. The scope of this increment is phases 0 and 1. Local changes on the owner's PC are outside the published revision.

| Area | Current behavior and evidence | Implementation consequence |
| --- | --- | --- |
| Web and HTTP | Next.js 14 App Router, React 18, five Arabic analysis pages, shared charts and fetch client. Four FastAPI routers under /api/v1/egx. The browser defaults to localhost. | Retain URLs, screens and response fields. Use a relative API URL at build time behind the hosted gateway. |
| Price acquisition | Yahoo requests daily .CA bars. Investing and its legacy resolver use web endpoints. DirectFN recovers selected completed sessions. Stooq and EGID return empty results. Strict Investing provider classes exist but the default manager instantiates other classes. | Audit identity at the ingestion boundary. Two adapters using the same upstream are not independent confirmation. Confirm licensed use, actual delays, adjustments and timestamp semantics before enabling a scanner. |
| Validation and time | StockPlansService excludes future and non-session rows. The provider/cache path validates HLCV but trusts row order and last date. Lag calculation treats a later date as zero. Missing volume defaults to zero and infinity passes some bounds. The market endpoint hardcodes UTC+3 in winter. | Centralize completed-session selection for network and cache. Preserve questionable finite opens as references. Separate session date from an executable quote timestamp. |
| Deterministic analysis | indicators, technical_rating (EGX26_V1), trade_plan, decision_engine, breakout_entry, risk_manager and owner_add_on implement indicators, pullback and breakout plans, sizing and position checks. Market depth is manual. Company profiles are special-cased and corporate events use a small static registry. | Reuse existing engines and their warmups. Keep the 1.5% risk and 20% allocation defaults. Add financial statements, corporate actions and source dates only when available. |
| Persistence | SQLAlchemy/SQLite, unique ticker/session, startup seed and BIOC correction archive. Read-only inspection of committed SQLite found only 177 security identities and 2,406 daily candles, no user, credential, portfolio or order tables. SQLite quick_check passed. | Separate writable data from the Git snapshot, back up before upgrades, and version additive migrations. Schema inspection cannot certify all Git history. |
| Security and runtime | Wildcard CORS with credentials. Direct FastAPI access can edit EOD data. There is no identity layer, broker, scheduler, portfolio ledger or notification worker. Local launcher binds backend to loopback. | Gate hosted UI and API with owner authentication and HTTPS. Keep credentials out of forwarded requests, reject foreign-origin writes, keep internal services private. |
| Performance | Directory issues per-symbol latest/count queries; plans loop through securities, load history and calculate ratings. Refresh can synchronously try multiple providers with network timeouts. | Batch directory reads, keep interactive plans cache-first, move scheduled fetches to a separate worker with provider quotas. Benchmark before selecting scanner frequency. |
| Tests and dependencies | No Python requirements manifest. Some tests assume startup seeding or call live providers. Two files outside backend/tests perform network and file writes at import. | Use an isolated DB, run the actual backend/tests suite, preserve external tests separately from deterministic fixtures, and never collect operational scripts as tests. |

## Recorded baseline

Python 3.12, Node 24, Next 14.2.35. Installed inferred Python dependencies in an isolated environment after the first run reported missing pytest. Used npm ci with the tracked lockfile. TypeScript and production build passed. Backend requests to external market providers were disabled for a reproducible outage scenario. No external price was verified in that run.

| Starting state | Result |
| --- | --- |
| Direct copy of the tracked DB | 206 passed, 11 failed, 1 skipped. Two directory tests expect AMES before the startup seeder runs. |
| Fresh copy after normal FastAPI startup | 208 passed, 9 failed, 1 skipped. |
| Frontend | npm run type-check and npm run build both passed. |

The seeded failures are three live historical-provider tests, the real-stock indicators test, two runtime checks requiring current COMI data, and three existing assertions about trade-plan actionability or KORA reason wording. Their names and interpretation appear in TECHNICAL_DASHBOARD.md and the test modules. The three decision assertions must be reconciled with intended strategy behavior independently of timestamp freshness.

## Integration evidence

Thndr documents an OAuth MCP endpoint at https://mcp.thndr.app/mcp. The owner selects tools and confirms access in the Thndr mobile app. Portfolio, cash, orders, trades, watchlists, prices and charts are documented. Some reads include savings balances and require explicit scope selection. Trade proposal creation/tracking/cancellation is rolling out by account. An existing open-order cancellation is a distinct write. Never grant either class of writes to a scanner. Trade proposals require individual mobile approval. Quotes can be delayed. No fixed market delay, per-minute quota, headless custom-client registration or available tools for this user's account were established. Discover granted tools after OAuth. Do not borrow another client's identity. Start read-only, fall back to manual review, and reject unknown quote age for real-money proposals.

Sources: https://docs.thndr.app/how-it-works, https://docs.thndr.app/tools, https://docs.thndr.app/troubleshooting, https://docs.thndr.app/clients/chatgpt.

OpenAI's Python SDK supports Responses API structured parsing with a Pydantic model. Phase 3 will send a minimal verified snapshot to a configurable model, with no order tools. Validate structured output, handle refusal/timeout locally, meter tokens and pre-reserve a bounded cost before each request. Cache by data, model, schema and policy version. Never send broker credentials. Sources: https://developers.openai.com/api/docs/quickstart and https://developers.openai.com/api/docs/guides/structured-outputs.

Public accessibility does not establish rights for commercial reuse or ongoing redistribution. Investing's terms restrict storage and use of its market information. No contracted intraday feed, depth entitlement, or redistribution grant was supplied for Yahoo, DirectFN, Investing, Stooq or EGID. Verify permissions with each provider before hosted data collection. Source: https://cdn.investing.com/about-us/terms_and_conditions.pdf.

## Delivery sequence and acceptance

| Phase | Work and primary files | Verification before progressing |
| --- | --- | --- |
| 1 | Restrict CORS, add a private HTTPS owner gateway, isolate mutable SQLite, record manual corrections via an additive migration, share EOD validation, document install and backup. Touch core config/database, API, market services, deployment config, tests and README. | Verify unauthorized access and origin rejection, protected normal entry points, snapshot integrity, migration re-run, invalid/stale bars, compatibility and frontend build. |
| 2 | Add integrations/thndr_mcp.py and licensed quote adapters with identity, exchange, currency, source time, delay class, session state and entitlement. | Mock grant discovery, revoke/expiry, missing tools, quotas, outages and delayed prices. Only a verified executable feed can pass the independent intraday gate. |
| 3 | Add integrations/openai_client.py and services/ai_decision_engine.py with schema-bound Egyptian Arabic explanations. | Test fallback without keys, rate/cost budgets, refusals, untrusted news, invariance of deterministic decisions. |
| 4 | Extend risk settings, portfolio exposure and Sharia screening with sources, threshold version and screening date. | Test fees, gaps, concentration, kill switch, missing statements and rejection of unverified new trades. |
| 5 | Add scanner, notification outbox and dedicated worker. Evaluate a single scheduler with database leases and unique scan windows before introducing Celery/Redis. | Cross-process duplicate suppression, restart recovery, active-session constraints, provider frequency and idempotent alerts. |
| 6 | Add a segregated paper ledger and backtesting using point-in-time universes, corporate actions, next-eligible fills, settlement and realistic fees. | Reconcile cash and holdings, prevent duplicate fills, verify walk-forward splits and benchmark alignment. |
| 7 | Add requested bilingual RTL dashboard routes, portfolio, Sharia, notifications and PWA; never cache private APIs or executable quotes offline. | Desktop/mobile navigation, offline state, accessibility and alert deduplication. |
| 8 | Add expiring order proposals, explicit approval per order, fresh quote/balance/risk revalidation and broker status reconciliation. | Mock all broker writes. Require idempotency and retain an audit trail. Enable manual handoff when an official workflow is unavailable. |
| 9 | Deploy separate long-running services with persistent storage, backups, monitoring and secrets. Consider PostgreSQL before multiple writers. | Restore drill, regression, security and data-entitlement review. Select host, budget, official feeds and notification accounts before deployment. |

Cost drivers for a later deployment are an always-on service and persistent storage, market-data entitlements, optional message delivery and OpenAI input/output tokens. This increment provisions no paid resources. A credible monthly estimate requires a selected host, usage budget and provider quotation.

## Official tools to verify against the account in phase 2

| Operation | Documented surface | Condition to implement |
| --- | --- | --- |
| Portfolio, available cash, trades and orders | Account and portfolio reads after the owner selects scopes | Inspect actual payload fields for cost basis, realized P&L and pending orders. Unknown fields stay unavailable. |
| Watchlist and market context | get_watchlist, get_market_status, get_market_watch, get_assets_info, get_price_history | Instrument info includes a delayed price. Bid/ask snapshots do not demonstrate executable freshness or Level-2 entitlement. |
| Fees and dividends | calculate_order_fees, get_asset_dividends | Preserve provider time, units and instrument identity. Revalidate fees per proposal. |
| Trade proposals and outstanding orders | Trade proposal tools are rolling out. cancel_order is a separate write. | Read-only by default. Never submit a proposal, cancel an open order or request a savings transfer while testing. Each real change requires explicit user approval. |

The existing live-analysis endpoint accepts manual prices and can return a conditional decision such as DO_NOT_CHASE. Its decisions lack an intraday entitlement and its guards are not sufficient for order approval. The plans service separately blocks inactive securities. Introduce one shared trading-restriction check before adding proposals. Market calendars currently embed closure dates through 2026 and a fixed regular close. Verify special hours and newly announced closures before unattended scans.

## Phase 1 implementation and checks

The gateway uses Caddy's bcrypt owner authentication over HTTPS for the UI and API. It validates the Origin of writes and strips owner credentials before proxying. A protected ingress is required for hosting. The local loopback API retains its previous calling convention. The frontend can use its existing build-time API setting for same-origin access. No frontend redesign was required.

The market snapshot retains its original Git blob. The writable default lives in backend/instance. The correction journal is additive and committed atomically with candle changes. One previous test fixture supplied a TEST ticker for an EGAL request and included weekends while claiming 60 trading sessions. Its inputs now use EGAL and 60 trading dates; the original fallback expectations remain.

| Verification | Observed result |
| --- | --- |
| Controlled provider outage after startup | Before 208 passed / 9 failed / 1 skipped. After 231 passed / 9 failed / 1 skipped. Identical failing test IDs. |
| Normal network after startup | Before 210 passed / 7 failed / 1 skipped. After 233 passed / 7 failed / 1 skipped. The seven failing IDs match: two tests require Yahoo even when Investing supplies a fallback, one requires 200 indicator sessions, one omits DO_NOT_CHASE from its allowed API responses, and three are the decision assertions above. The skipped fixture is an overextended synthetic setup. Provider responses can vary by run. |
| Frontend | TypeScript and the production build passed before and after. The hosted build used /api/v1. |
| Storage | Repeated migration preserved all rows of both original tables. Concurrent backup tests produced one complete copy. The tracked SQLite SHA-256 matched the base revision. |
| Private access | Caddy 2.11.9 passed authentication, rejection of missing/foreign Origin, verified local TLS, credential stripping and cache checks. A second smoke run used the real built Next.js server and FastAPI. The authenticated directory and AMES lookup returned 200. A trusted-origin malformed write reached input validation (422), an untrusted write was rejected. |
| Availability | No brokerage credentials, market-data entitlement or model key were used. Deployment, continuous monitoring and broker approval remain future work. |

Files added include README.md, ARCHITECTURE.md, CHANGELOG.md, IMPLEMENTATION_PLAN.md, .env.example, deploy/Caddyfile, backend/requirements*.txt, backend/pytest.ini, the Alembic environment and first revision, core/sqlite_backup.py, models/candle_revision.py and the data-foundation and HTTPS gateway tests. Existing changes cover core configuration and database setup, the FastAPI app, stock/market/manual-analysis routes and schemas, seeding, validation, calendar, provider manager and Yahoo volume handling, stock plans, relevant tests and Git ignore rules.
