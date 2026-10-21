# Deployment · v0.2

## Host development

Use Python 3.11+ for the backend and Node.js 22+ for the React build. If Node is
absent, use the Docker-based frontend build command in the README. Start from the
existing checkout; don't overwrite its private `.env` or reprovision its working
device credentials when upgrading. Stop old Uvicorn, back up, install the locked
Python dependencies, migrate and create an administrator as documented in README.

The frontend serves from `FRONTEND_PATH` (default `../frontend/dist` relative to
backend/). Build with `npm ci && npm run build` from frontend/, then start FastAPI.
`GET /` is the dashboard; `/docs` is API documentation. If assets were absent when
the process started, restart after building. Path-prefixed hosting is unsupported.
Use one origin for dashboard/API. Vite's development server proxies `/api` to
loopback port 8081; production uses the FastAPI-served build. Adjust the dev proxy
if changing the backend port. Live backend values appear read-only in Configuration;
change environment values and restart to apply them.

Set PUBLIC_BASE_URL to an origin reachable by the gateway and include its hostname/IP
in the JSON ALLOWED_HOSTS list. Bind Uvicorn to `0.0.0.0` or the lab interface for
LAN access. A loopback listener accepts only host-local traffic. Port 8081 avoids
the previous hawkBit listener on 8080; check actual listeners before changing ports.
Don't terminate the old hawkBit service merely to start a development instance.

## Docker Compose

Requires Docker Engine and the Compose v2 plugin. The image builds the React app
in a Node stage and copies its static build into a non-root Python runtime.
From repository root:

```bash
# Fresh setup only: copy and edit backend/.env first; don't overwrite an existing file.
docker compose build
docker compose run --rm api alembic upgrade head
docker compose run --rm api ota admin-create admin
docker compose up -d api
```

Compose stores SQLite and private firmware in the named `/data` volume and explicitly
sets the in-image frontend path. Default publication is `127.0.0.1:8081:8080`.
For controlled LAN use, export BIND_ADDRESS as the host's lab interface IP, set
HTTP_PORT as needed, and edit backend/.env's public origin/allowed hosts accordingly.
For PostgreSQL set `OTA_CONTAINER_DATABASE_URL=postgresql+psycopg://...` in the
Compose shell/secret environment; this avoids accidentally using a host-relative
SQLite URL inside the container. Keep credentials out of Git. Compose configuration
intentionally overrides the host's DATABASE_URL/storage/frontend paths.

Bootstrap and token files are privileged operations. `ota target-create ...
--token-file /data/private-new.token` creates a private file inside the named volume;
provision it through your secure operator process, never shared logs. Database and
volume backups are required before upgrades. Do not use `docker compose down -v`
unless you intend to destroy retained data.

Image build/container smoke checks were executed with Docker Engine directly.
Compose v2 is missing on the development host, so orchestration itself was not run.

## Production-oriented HTTPS

1. Provision PostgreSQL, a least-privilege application account, private object storage
   directory and a tested backup/recovery procedure. Run migrations once through
   a controlled job before launching workers. Never run tests against production.
2. Set APP_ENV=production, an externally reachable HTTPS PUBLIC_BASE_URL and explicit
   ALLOWED_HOSTS. Production validation rejects SQLite/HTTP/loopback public origins.
3. Adapt deployment/nginx/ota.conf.example to the real hostname and mount a trusted
   certificate/key. It expects backend `api:8080` on a private network. Expose only
   TLS publicly; protect backend and DB with network controls.
4. Align MAX_UPLOAD_SIZE_MB and the proxy upload location's client_max_body_size,
   timeouts and disk capacity. The upload route disables proxy buffering. Keep
   all normal DDI JSON endpoints bounded and never publish a storage alias.
5. Run Uvicorn with --no-proxy-headers. Forwarded values are stripped/ignored; links
   use PUBLIC_BASE_URL. If client-IP forwarding is later added, explicitly restrict
   trusted proxy addresses and test spoofing before enabling it.
6. Create a private administrator, provision target certificate trust and set target
   ssl=true/ssl_verify=true. Revalidate no-assignment polling before real firmware.

TLS on the actual gateway and reverse-proxy certificate renewal were not tested.
Production readiness also requires deployment-specific throttling/capacity,
restoration, retention and monitoring. The local functional test suite is evidence
for the implemented behavior, not proof of large-fleet or physical update safety.
