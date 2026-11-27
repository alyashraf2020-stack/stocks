# Changelog

## Security update · Next.js 16 and React 19

- Updated Next.js to 16.4.6 and React/React DOM to 19.3.1. Updated PostCSS and resolved patched `source-map-js` and `postcss-selector-parser` releases within their supported ranges.
- Migrated dynamic App Router page parameters, generated route types, and replaced the removed `next lint` command with ESLint flat config.
- Added production and full dependency audits on Node.js 22 and 24. Windows CI installs the previous personal release and upgrades it through the original `UPDATE.bat`, checking saved settings, the encrypted vault, SQLite and backups.

## AI trading assistant foundation

- Recorded the baseline audit and official Thndr/OpenAI integration constraints.
- Isolated the writable market database and added a verified online backup command and an additive correction journal migration.
- Validated completed EOD data across providers, cache, charts, directory and plans. Manual prices retain explicit provenance on the live-analysis API.
- Batched the directory candle query and fixed the Cairo UTC offset and market-close boundary in the status response.
- Added a single-owner HTTPS gateway, restricted browser write origins, and documented private setup and regression testing.

## Phase 2 · Thndr and market data

- Added a repeatable offline regression suite, opt-in provider contract checks and GitHub Actions checks for Python, TypeScript and the production build.
- Corrected strategy assertions for fresh closes outside entry zones, completed targets and a valid pullback re-entry.
- Added read-only Thndr OAuth and MCP integration with encrypted persistence, PKCE, scope checks, refresh, revocation and throttling.
- Added independently classified broker quotes and Arabic settings and portfolio pages.

## Phase 3 · OpenAI interpretation and opportunity analysis

- Added optional tool-free structured interpretation with a deterministic Egyptian Arabic renderer and protected stock and portfolio analysis routes.
- Added atomic budget accounting, model fallback, private cache and request deduplication.
- Added an AI dashboard, opportunity ranking and controls on stock and portfolio pages.
- Kept phase 2 quote and authorization gates in the analysis path and verified the SWDY provider coverage failure separately.

## Phase 4 · Portfolio risk and Islamic mode

- Added owner risk policy, Decimal sizing, cost and gap estimates, exposure and historical valuation checks, and review-only holding scenarios.
- Added EGX-methodology screening with dated sources, expiry, explicit unknown results, and independent index membership evidence.
- Integrated risk and Islamic entry gates with analysis and rankings, and added the Arabic portfolio risk and screening pages.

## Phase 5 · Market scanner and alerts

- Added a standalone SQLite scheduler, fenced worker leases, heartbeats, recovery, bounded evaluation and scanner history.
- Added cache-only completed-session scans for the market, watchlist, manual holdings or authorized Thndr holdings, with independent delayed-quote observations and checked calendar coverage.
- Added risk and Sharia publication gates, deterministic signal transitions, optional budgeted AI interpretation and transactional in-app alerts.
- Added Arabic scanner, watchlist, notification and settings pages, and integrated results with opportunities and existing owner pages.
- Added an external delivery adapter boundary. Telegram and licensed intraday ingestion remain pending.

## Phase 6 · Virtual execution and historical validation

- Added multiple virtual accounts, order and fill audit, cash reservations and deposits, settlement, protective exits and independent paper reconciliation.
- Added approved dataset versions, five close-only strategies, advanced risk and historical Sharia gates, durable backtest jobs, benchmark comparisons, metrics, stress and chronological validation.
- Added protected Arabic dashboards, CSV and JSON output, and a validation report with no claimed profitability.

## Phase 7 · Mobile access, delivery and data readiness

- Added an installable Arabic PWA, privacy-safe offline shell, mobile navigation and unified operations dashboard.
- Added expiring Telegram pairing, encrypted browser push subscriptions, independent channel delivery leases and settings.
- Added CSV and JSON preview, immutable authorized EOD imports, coverage and source diagnostics, and a scheduled private inbox.
- Added an owner health view and service-manager examples. Real market data and external delivery commissioning remain deployment tasks.

## Phase 8 · Local order proposal review

- Added immutable conditional drafts, exact single-use local review, structured readiness checks, and proposal audit history.
- Added Arabic owner screens, opt-in scanner drafts and mobile review notifications.
- Preserved the independently authorized read-only Thndr session and disabled all brokerage handoff in this release.

## Phase 9 · Free personal operation

- Added Windows install, start, stop, restart, status, update, backup, restore and rollback launchers, plus optional logon startup.
- Added a private Tailscale Serve ingress that reuses Caddy owner authentication, Origin checks and cache policy. Personal service environments disable OpenAI.
- Added Windows runner checks for launchers, loopback-only services, worker restart and backup. Broker writes remain disabled.

## Phase 11 · EODHD Free analytical data

- Added owner-only EODHD configuration, encrypted local credentials, usage checks, manual synchronization, and opt-in scheduled backfill.
- Added a persistent UTC quota and an account usage check before every billable call. EODHD observations feed the analysis and scanner without granting execution, backtest dataset, or live-price eligibility.
