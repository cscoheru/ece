# ECE Demo Deployment Runbook

> **Scope lock (cut-045, Codexd directive §0)**: This is the **Demo Deployment Profile**
> for the founder's own server. It is **not** a customer-private installer.
> No multi-tenant, no K8s, no customer data-out-of-domain guarantees, no
> migration / backup SLA. Customer-private deployment is a future capability
> — see View C "Customer Private Deployment" badge (⬜ 规划中).

This runbook walks the founder (or an engineer on call) through bringing up
a stable, demoable ECE deployment on a single Linux server.

---

## 1. Server prerequisites

- 2 vCPU, 4 GB RAM, 20 GB disk (demo fixture data is small)
- Linux (Ubuntu 22.04+ or equivalent)
- Docker Engine 24+ and docker compose v2
- nginx 1.18+ (installed; certbot optional for HTTPS)
- Outbound HTTPS to GitHub for `git clone`
- Inbound 80/443 open to internet (nginx reverse proxy serves the SPA)

## 2. Clone the repository

```bash
git clone https://github.com/cscoheru/ece.git /opt/ece
cd /opt/ece
git checkout main
```

## 3. Prepare environment variables

```bash
cp deploy/.env.example deploy/.env
$EDITOR deploy/.env
```

Required edits:
- `POSTGRES_PASSWORD`: set to a strong random string (e.g. `openssl rand -base64 24`)
- `ECE_SERVER_TODAY_ANCHOR`: set to today's date in strict `YYYY-MM-DD` format
  (e.g. `2026-09-22`); the API enforces canonical round-trip.
- `DEMO_DOMAIN`: the public hostname (e.g. `corln.rana.asia`)

`deploy/.env` is in `.gitignore` (created automatically by `git init`); do not
commit it. The template `deploy/.env.example` is the only env file in git.

## 4. Start the API + database

```bash
docker compose -f deploy/docker-compose.demo.yml --env-file deploy/.env up -d
```

This brings up:
- `api` service — FastAPI app, **published on host loopback `127.0.0.1:8000`**
  (NOT `0.0.0.0`; nginx proxies `/api/` and `/healthz` to it)
- `db` service — `pgvector/pgvector:pg16`, port 5432 inside the docker
  network only (no host port; R3-B2 fix: official pgvector image, no
  manual tagging needed)

Verify both services are healthy:

```bash
docker compose -f deploy/docker-compose.demo.yml ps
```

Both should show `(healthy)`. If the API is unhealthy, check
`docker compose -f deploy/docker-compose.demo.yml logs api`.

## 5. Run migrations + seed the three-domain fixtures

The demo compose database is **only reachable from inside the api
container** (no host port). Therefore alembic and seed scripts must run
inside the api container. The reset script (`deploy/scripts/reset-demo-fixtures.sh`)
handles this — see R3-B2 fix below.

```bash
./deploy/scripts/reset-demo-fixtures.sh
```

This runs (inside the api container):
1. `alembic upgrade head` — schema migration (R3-B2: via `docker compose
   run --rm api alembic upgrade head`, NOT host-installed alembic)
2. `seed_v0_spike_fixture.py` — procurement fixtures
3. `seed_knowledge_fixture.py` — knowledge-management fixtures
4. `seed_compliance_fixture.py` — compliance fixtures

Each seed script is idempotent — re-running the reset before a demo is safe.

## 6. Configure nginx

```bash
sudo cp deploy/nginx/corln.rana.asia.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/corln.rana.asia.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

The config listens on port 80 by default (with certbot-ready `/.well-known/acme-challenge/`).
It serves `/opt/ece/demos/spa/` as the SPA root (path matches the README
clone target — R3-B1 fix) and reverse-proxies `/api/` and `/healthz` to
the api service on `127.0.0.1:8000` (host loopback bind from compose —
R3-B1 fix; replaces the previous topology where nginx targeted an
unpublished docker port and produced 502).

For HTTPS (recommended for demos):

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d corln.rana.asia  # auto-issues cert + edits nginx
```

Certbot adds the HTTPS server block automatically and renews via cron.

## 7. Health check

```bash
curl -fsS http://127.0.0.1/healthz
# expected: "ok" (or similar JSON status)
```

Through the public URL:

```bash
curl -fsS https://corln.rana.asia/healthz
```

## 8. Same-origin deployment smoke

Run the cut-045 deployment smoke against the live URL:

```bash
DEMO_BASE_URL=https://corln.rana.asia \
    .venv/bin/python scripts/cut_045_demo_deployment_smoke.py
```

Expected output:

```text
PASS=10 SKIP=0 FAIL=0
```

This script verifies (1) SPA reachable at origin, (2) all three domains
discoverable, (3) three valid cases pass, (5) three denied cases return
no_permission, (7) strict-date 422, (9) zero external CDN.

## 9. Reset fixtures before a demo

```bash
./deploy/scripts/reset-demo-fixtures.sh
```

Re-running the seeds takes a few seconds; safe to invoke between demo
sessions.

## 10. Tail logs

```bash
docker compose -f deploy/docker-compose.demo.yml logs -f api
docker compose -f deploy/docker-compose.demo.yml logs -f db
```

## 11. Common troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `/api/v1/demo/domains` returns 502 | `api` service not running, or nginx proxying to an unpublished container port (R3-B1 lesson) | `docker compose ps`; check `docker compose logs api`; confirm `127.0.0.1:8000` is bound (`ss -tlnp \| grep :8000`); verify `DATABASE_URL` env var |
| SPA shows raw JSON instead of HTML | nginx `root` wrong path (R3-B1 lesson: must match clone path `/opt/ece`) | Confirm `/opt/ece/demos/spa/index.html` exists and is readable by the nginx user; if cloning elsewhere, update `root` in `corln.rana.asia.conf` |
| `403 Forbidden` on `/api/` | CORS / preflight — but same-origin so it shouldn't fire | Verify `Origin` header == `Host` in browser DevTools; check `$host` proxy_set_header |
| `/healthz` returns 404 | nginx `/healthz` block missing | Confirm `location = /healthz { proxy_pass ... }` present; reload nginx |
| certbot renew fails | Port 80 not reachable from internet during renewal | Verify inbound 80 is open; temporarily disable other 80 listeners |
| Postgres "out of memory" | 4 GB RAM is the floor | Upgrade to 8 GB or lower `shared_buffers` in postgres.conf |
| `ECE_SERVER_TODAY_ANCHOR` rejected (422) | Non-canonical YYYY-MM-DD (e.g. `20260922`) | Use exact `YYYY-MM-DD` form: `2026-09-22` |
| Demo smoke reports `no_permission` for a "valid" user | Seed fixtures not loaded | Re-run `./deploy/scripts/reset-demo-fixtures.sh` |
| `alembic upgrade head` not found on host | reset script used host-installed alembic (R3-B2 lesson) | Run reset script (it routes through `docker compose run --rm api`); do not invoke host alembic |

---

**Done**. The deployment is ready for demos. Customer-private deployment
is a future cut (View C "Customer Private Deployment" ⬜ 规划中).