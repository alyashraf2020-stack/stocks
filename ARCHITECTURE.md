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
