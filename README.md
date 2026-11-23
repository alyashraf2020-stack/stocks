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
