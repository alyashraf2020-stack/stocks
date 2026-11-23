# Changelog

## AI trading assistant foundation

- Recorded the baseline audit and official Thndr/OpenAI integration constraints.
- Isolated the writable market database and added a verified online backup command and an additive correction journal migration.
- Validated completed EOD data across providers, cache, charts, directory and plans. Manual prices retain explicit provenance on the live-analysis API.
- Batched the directory candle query and fixed the Cairo UTC offset and market-close boundary in the status response.
- Added a single-owner HTTPS gateway, restricted browser write origins, and documented private setup and regression testing.
