# Egyptian Exchange analysis platform

The existing Next.js and FastAPI application provides the EGX directory, stock reports, EGX26 technical ratings, charts, conditional plans and analysis using a manually entered broker price. The AI assistant branch starts with data integrity and private access. The implemented routes are listed at `/docs` on the backend.

## Run locally

Use Python 3.12 and Node.js 22 or 24. From a Python virtual environment, run these commands in `backend`.

```sh
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In `frontend`, run `npm ci` and `npm run dev -- --hostname 127.0.0.1`. Open http://localhost:3000. The Windows launcher uses the local analysis workflow. An API key is unnecessary for these features.

## Existing installations and backup

Stop processes on the previous branch before switching versions. If your laptop has a pending merge or modified database, preserve that working copy and make a separate checkout for review. For an existing SQLite database, use SQLite's backup API to preserve committed WAL data. From the new backend checkout, use the old database's actual absolute path:

```sh
python -m app.core.sqlite_backup /absolute/path/to/old/egx_platform.db /absolute/private/path/market-backup.db
```

On an in-place upgrade, the default first launch copies `backend/egx_platform.db` (including any owner-local changes at that path) into ignored `backend/instance/egx_platform.db`. It verifies SQLite integrity and publishes the copy atomically. The old file remains as a bootstrap snapshot. An existing runtime database always wins. Explicitly selecting the legacy snapshot path also resolves to the runtime copy. A separate checkout only contains the published historical snapshot. To use local history there, restore the verified backup to a new private path and export `DATABASE_URL` pointing to it before migration or startup.

The journal migration is additive. Production setup runs Alembic before the API, then a single API process seeds the existing directory on startup. The legacy local create_all workflow also creates the journal. The first release does not migrate an account or connect to a broker. To restore, stop the API, back up its current state, restore to an unused file, verify integrity and row counts, set DATABASE_URL, and start the matching code revision. Backup files can contain sensitive user data. Keep backups private, encrypted and outside Git.

## Private HTTPS access

The supported hosted topology for this increment is a single-owner gateway. Bind the frontend and backend to loopback on the same host. Expose only Caddy's HTTPS listener and any HTTP listener needed for certificate issuance. Direct access to the local API assumes a trusted local user. Never forward ports 3000 or 8000 from the public network.

1. Build the frontend with `NEXT_PUBLIC_API_URL=/api/v1 npm run build`. Start it with `npm run start -- --hostname 127.0.0.1`. Build-time environment matters because the browser calls the API.
2. Start the migrated backend as shown above. Keep Caddy's administration listener private.
3. Set `APP_HOST` to a DNS hostname and `OWNER_PASSWORD_HASH` to the bcrypt output of the interactive `caddy hash-password` command in the gateway service environment. The owner's username is `owner`. Use a password manager. Provide these settings before validating or starting the gateway. The example environment file is a template, not a secret store.
4. Run `caddy validate --config deploy/Caddyfile`, then run Caddy with that configuration. Automatic public HTTPS requires DNS and inbound certificate validation. Keep Caddy's data directory persistent.
5. The browser prompts for the owner credential. The gateway verifies it on every request and removes Authorization before forwarding. Writes must carry an exact same-origin HTTPS Origin header. Intentional command-line writes through this gateway must supply that same Origin and owner authentication. Rotate the hash and reload Caddy to revoke the old password. There are no bearer tokens or application sessions to retain.

This configuration is a tested ingress foundation. Live provider licensing, ongoing patch management, an independent worker, operational rate limiting, restore scheduling, broker OAuth and per-order approvals are later deployment gates.

## Verification

Use a disposable database copy. Never run the network-dependent test suite against a private database. From `backend`, set DATABASE_URL to that copy, run `python -m alembic upgrade head` and `python -m app.services.seeder`, then run `python -m pytest -q`. With Caddy on PATH, the suite also runs an actual local HTTPS authentication and CSRF test. From `frontend`, run `npm run type-check` then `npm run build`. Existing tests that require current external prices can fail during outages. See IMPLEMENTATION_PLAN.md for the measured baseline and known failures.

## Project documents

- ARCHITECTURE.md describes the running services, boundaries and data lifecycle.
- IMPLEMENTATION_PLAN.md contains the audit, baseline and phased acceptance criteria.
- TECHNICAL_DASHBOARD.md and STOCK-PLANS.md describe existing calculations and screens.
- CHANGELOG.md records this increment.

## Phase 2 · Connect Thndr for read-only access

Use the private HTTPS gateway described above. In the backend service environment, set `THNDR_REDIRECT_URI=https://YOUR_HOST/api/v1/integrations/thndr/callback` with the exact gateway origin. Generate a Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and keep it in `THNDR_ENCRYPTION_KEY` on the backend only. Generate a separate high-entropy random value for `INTEGRATIONS_GATEWAY_SECRET` and give the same value to Caddy and FastAPI through their private service environments. Keep the front and back ends on loopback. If configuring proxy access logs, exclude the OAuth callback query string.

The encrypted state file defaults to `backend/instance/thndr.enc`. Set `THNDR_PRIVATE_DIR` to use another service-owned directory on a local persistent filesystem. Keep its backups and the encryption key in separate private locations. The browser communicates only with the gateway and never receives broker credentials.

Open `/settings/integrations`, choose **ربط ثاندر**, sign in with Thndr and confirm the read tools on your phone. Thndr's OAuth metadata advertises dynamic registration, S256, refresh and revocation. Some clients require Thndr to approve their callback address. If registration or redirect is refused, verify the exact HTTPS callback with Thndr. The supported alternative is [Thndr in ChatGPT](https://docs.thndr.app/clients/chatgpt), where account data stays in that connector. Never reuse another client's registration or export its access token.

Open `/portfolio` and choose **مزامنة المحفظة**. Values are displayed only when the authorized tool provides a recognized, validated field. A missing value stays unavailable. Thndr market prices are treated as delayed or unverified. The timestamp shown beside a quote is its source timestamp. **فصل ثاندر** immediately clears portfolio data from the app and requests upstream revocation. If Thndr is down, local access remains blocked and you can retry revocation.

### Offline regression and external smoke checks

From `backend`, run `python -m pytest -q`. The suite seeds a disposable database and blocks external sockets. Add Caddy to PATH to run the real TLS gateway test. The GitHub Actions job also confines Python and native dependencies to loopback. Frontend checks run `npm run type-check` and build with the same-origin API configuration.

External provider checks are opt-in with `python -m pytest -o addopts='' -m external -q`. They verify real provider behavior, can fail during feed outages or insufficient coverage, and use a disposable database. Brokerage OAuth and account data are mocked in the regression suite. Commissioning the live connection requires the owner's HTTPS deployment, Thndr acceptance of its callback, and owner consent.

## Phase 3 · Analysis and optional OpenAI interpretation

Open `/ai-trading` from the single-owner HTTPS gateway. Stock pages also offer stock analysis, and the portfolio page can analyze positions already synchronized through Thndr. Price, cost basis, shares and total portfolio value can be entered manually if a brokerage account is unavailable. Manual prices and delayed Thndr prices carry their own labels. The system only presents conditional analysis. A verified real-time quote, order workflow, and live execution are outside this phase.

To enable OpenAI, set `AI_ENABLED=true` and `OPENAI_API_KEY` in the backend process environment. AI is off by default. The default is the dated `gpt-5.4-mini-2026-03-17` snapshot, which supports Responses and Structured Outputs. Standard reference rates verified on 24 November 2026 were USD 0.75 input and USD 4.50 output per million tokens. Confirm model access and the current rates before enabling billing. A custom `OPENAI_MODEL` requires both `AI_INPUT_USD_PER_MILLION` and `AI_OUTPUT_USD_PER_MILLION`. Set both to override the bundled reference rates. [Model and pricing](https://developers.openai.com/api/docs/models/gpt-5.4-mini) · [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)

Daily and monthly caps default to USD 0.25 and USD 3. Settings also control output tokens, timeouts, cache TTL, per-ticker analysis interval and total request frequency. Keep `AI_LEDGER_PATH` on a private, persistent local filesystem shared by workers on this host. The default is `backend/instance/ai_usage.sqlite3`. Keep the ledger when restarting so usage carries forward. Daily and monthly aggregation use Cairo time. Reservations use a conservative prompt-size bound and reserve for two attempts. Charges use reported tokens at the configured standard rates, with ambiguous failures retaining an estimate. The dashboard reports estimates and token totals, and provider billing can differ. The circuit breaker cools down for 90 seconds after three recent upstream failures.

`/opportunities` ranks current cached EOD plans with no OpenAI requests. Its optional Thndr view adjusts ranking for authorized exposure. A single portfolio review calculates up to 25 positions and requests at most one model interpretation for its highest-ranked eligible symbol. Fundamental data and order-book liquidity remain explicitly unavailable in this phase. Technical rating agreement describes the indicators. It does not estimate profit probability. The offline suite exercises the actual SDK against mocked Responses transport and never makes a paid API call.
