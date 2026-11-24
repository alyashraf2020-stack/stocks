# Changelog

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
