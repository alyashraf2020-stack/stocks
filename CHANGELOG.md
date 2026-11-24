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
