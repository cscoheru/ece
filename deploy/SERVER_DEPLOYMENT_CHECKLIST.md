# ECE Demo Server — SERVER DEPLOYMENT CHECKLIST (12 Phase)

> **Scope lock (cut-045R2, Codex directive §0)**:
> - This is the **Demo Deployment Profile** for the founder's own server.
> - It is **NOT** a customer-private installer, NOT multi-tenant, NOT K8s.
> - Customer-private deployment is a future event (View C `Customer Private Deployment ⬜`).
>
> **State model (cut-045R2, 2026-09-23)**:
> - `cut-045` is the **terminal cut** for the demo platform scope.
> - **There is no `cut-046`.** If you find a defect, open a `cut-045R*` rework cycle.
> - Next step after Codex PASS is operational closure / customer material, not a new implementation cut.
>
> **Who runs this**: The founder (or an engineer on call). Claude does **NOT** execute
> this checklist — Claude only wrote it. The completion gate (Phase 9) requires
> real output from your server.
>
> **Secrets discipline** (applies to **every** phase below):
> - **NEVER** commit `deploy/.env` to git (it is in `.gitignore`).
> - **NEVER** paste real passwords / private keys / server passwords in:
>   - chat messages, commit messages, repo files, CI logs.
> - For STOP gates, paste **non-secret** output only (counts, status lines, `dig` results).
> - If a STOP gate requires a secret, paste the **command name + last 3 chars** only (e.g. `POSTGRES_PASSWORD=…wQ2`).

---

## Phase 0 — Preflight (Server prerequisites)

**Goal**: Confirm the server meets every prerequisite before any code change.

**Commands** (run each, capture output):

```bash
# OS / kernel
uname -a
cat /etc/os-release | head -5

# Public IP (what DNS should resolve to)
curl -fsS https://api.ipify.org && echo

# SSH access to this server (you are here, so this should be true)
echo "SSH access: yes (you are connected)"

# Docker Engine + Compose v2
docker --version          # expect: Docker version 24+
docker compose version    # expect: Docker Compose version v2.x+

# nginx (will install in Phase 2, just confirm if preinstalled)
nginx -v 2>&1 || echo "nginx not installed yet (will install in Phase 2)"

# Ports 80 / 443 inbound reachable from internet
ss -tlnp | grep -E ':80|:443' || echo "ports 80/443 not yet listening"

# Outbound HTTPS to GitHub (needed for git clone in Phase 3)
curl -fsS -o /dev/null -w "%{http_code}\n" https://github.com
```

**Placeholders**:
- `<SERVER_PUBLIC_IP>` — what `api.ipify.org` returns. Memorize it; you will paste it in Phase 1.

**Expected output**:
- `uname -a` shows Linux x86_64, kernel ≥ 5.15
- `curl api.ipify.org` returns an IPv4 address
- `docker --version` ≥ 24.x
- `docker compose version` is v2 (e.g. `v2.27.x`)
- `curl github.com` returns `200`

**Common errors**:
- `docker: command not found` → install Docker Engine from <https://docs.docker.com/engine/install/>
- `docker compose version` is v1 (`docker-compose` with hyphen) → upgrade to Compose v2 plugin
- Port 80 / 443 blocked → open inbound 80 + 443 in the cloud security group / firewall
- No outbound HTTPS → check egress proxy / NAT

**🛑 STOP gate**: Paste the following in your report to Claude / Codex:

```text
Phase 0 preflight:
  OS = <paste uname + os-release lines>
  public IP = <paste IPv4 from api.ipify.org>
  Docker = <paste docker --version>
  Compose = <paste docker compose version>
  nginx = <preinstalled YES/NO>
  Inbound 80/443 = <open YES/NO>
  GitHub reachable = <200/other>
```

**Do not proceed to Phase 1 until every line is filled in.**

---

## Phase 1 — DNS

**Goal**: Verify `corln.rana.asia` resolves to `<SERVER_PUBLIC_IP>` from the **public internet** (not just from inside the server).

**Commands**:

```bash
# Resolve from public DNS
dig +short corln.rana.asia A

# Cross-check from a different resolver
dig +short corln.rana.asia A @1.1.1.1
dig +short corln.rana.asia A @8.8.8.8

# Optional: check propagation globally
# https://dnschecker.org/#A/corln.rana.asia  (web tool, manual)
```

**Placeholders**:
- None — `corln.rana.asia` is the canonical demo domain for this deployment.

**Expected output**:
- All three `dig` commands return the same single IPv4 address.
- That address equals `<SERVER_PUBLIC_IP>` from Phase 0.

**Common errors**:
- `dig` returns nothing → DNS A record missing at the registrar (e.g. Cloudflare / Namecheap / Aliyun DNS). Add an A record `corln.rana.asia → <SERVER_PUBLIC_IP>`.
- `dig` returns multiple addresses → you have stale records. Delete all but the one pointing to `<SERVER_PUBLIC_IP>`.
- `dig` returns the right IP from inside the server but wrong from public DNS → DNS cache propagation delay. Wait 5–30 min and retry.

**🛑 STOP gate**: Paste the following:

```text
Phase 1 DNS:
  dig +short corln.rana.asia = <paste IP>
  dig @1.1.1.1 = <paste IP or "mismatch">
  dig @8.8.8.8 = <paste IP or "mismatch">
  matches <SERVER_PUBLIC_IP>? = <YES/NO>
```

**Do not proceed to Phase 2 until `matches <SERVER_PUBLIC_IP>? = YES`.**

---

## Phase 2 — Server prep (install nginx + certbot; verify Docker)

**Goal**: Install nginx + certbot on the host; confirm Docker is ready.

**Commands**:

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx

# Confirm versions
nginx -v                                 # expect: nginx version: nginx/1.18+
certbot --version                        # expect: certbot 2.x

# Confirm docker compose v2 is the active plugin
docker compose version

# (Optional) Enable nginx to start on boot
sudo systemctl enable nginx
```

**Placeholders**: None.

**Expected output**:
- `nginx -v` prints `nginx version: nginx/1.18+`
- `certbot --version` prints `certbot 2.x.x`
- `docker compose version` prints `Docker Compose version v2.x.x`

**Common errors**:
- `Unable to locate package nginx` → `sudo apt update` first; check `sources.list`
- `certbot: command not found` → `python3-certbot-nginx` install failed; retry or use snap (`sudo snap install --classic certbot`)
- Port 80 already in use (`bind() to 0.0.0.0:80 failed (98: Address already in use)`) → another web server (apache / caddy) is running; stop it: `sudo systemctl stop apache2`

**🛑 STOP gate**: Paste:

```text
Phase 2 server prep:
  nginx -v = <paste>
  certbot --version = <paste>
  docker compose version = <paste>
```

---

## Phase 3 — Clone repo (to /opt/ece)

**Goal**: Clone the ECE repo at the canonical path nginx expects (`/opt/ece`).

**Commands**:

```bash
# Create the deploy root (must match the SPA root in deploy/nginx/corln.rana.asia.conf)
sudo mkdir -p /opt/ece
sudo chown "$USER":"$USER" /opt/ece

# Clone
git clone https://github.com/cscoheru/ece.git /opt/ece
cd /opt/ece
git checkout main

# Verify
git log --oneline -1
ls -la demos/spa/ deploy/
```

**Placeholders**: None — `cscoheru/ece` is the canonical fork; `main` is the deployment branch.

**Expected output**:
- `git clone` finishes with no error
- `git log --oneline -1` shows the latest commit hash on `main`
- `ls demos/spa/` shows `index.html` `app.js` `styles.css`
- `ls deploy/` shows `docker-compose.demo.yml` `nginx/` `.env.example` `scripts/` `README.md`

**Common errors**:
- `Permission denied (publickey)` or `could not read Username for 'https://github.com'` → repo is public; check outbound HTTPS to github.com (Phase 0). For private repos, set up SSH keys first.
- `fatal: destination path '/opt/ece' already exists` → you (or a previous run) already cloned. `cd /opt/ece && git pull`.
- Wrong branch → `git branch --show-current` should say `main`. If not, `git checkout main`.

**🛑 STOP gate**: Paste:

```text
Phase 3 clone:
  HEAD = <paste git log --oneline -1 line>
  demos/spa contents = <paste ls demos/spa/>
  deploy contents = <paste ls deploy/>
  current branch = main? = <YES/NO>
```

---

## Phase 4 — Environment (cp .env.example .env; edit values)

**Goal**: Create `deploy/.env` from the template, set real values.

**Commands**:

```bash
cd /opt/ece
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env        # owner-only read/write
$EDITOR deploy/.env          # edit the placeholders below
```

**Placeholders to edit in `deploy/.env`**:

| Variable | Example value | How to generate |
|---|---|---|
| `POSTGRES_USER` | `ece` | (template default — keep) |
| `POSTGRES_PASSWORD` | (24-char random) | `openssl rand -base64 24` |
| `POSTGRES_DB` | `ece` | (template default — keep) |
| `DATABASE_URL` | derived | **Leave as-is** — it is constructed from the three POSTGRES_* vars above |
| `ECE_SERVER_TODAY_ANCHOR` | `2026-09-23` | Today's date in **strict** `YYYY-MM-DD` format. The API enforces canonical round-trip and will reject anything else with 422. |
| `API_PORT` | `8000` | (template default — keep) |
| `DEMO_DOMAIN` | `corln.rana.asia` | Public hostname from Phase 1 |
| `ECE_LOG_LEVEL` | `INFO` | (template default — keep) |

**Security check (run after editing)**:

```bash
# Confirm .env exists with correct perms
ls -la deploy/.env

# Count non-comment lines (should be 7 variables + 2 derived = ~8)
grep -cE '^[A-Z]' deploy/.env

# Confirm it is gitignored (it must NOT be tracked)
git check-ignore deploy/.env && echo "OK: .env is gitignored" || echo "FATAL: .env NOT gitignored"
```

**Expected output**:
- `ls -la deploy/.env` shows `-rw-------` (mode 600)
- `grep -cE '^[A-Z]' deploy/.env` returns a positive integer (≈ 8)
- `git check-ignore` returns 0 + prints `OK: .env is gitignored`

**Common errors**:
- `ECE_SERVER_TODAY_ANCHOR=2026-09-23 12:00` (with time) → API rejects with 422. Use exact `YYYY-MM-DD` with no time component.
- `POSTGRES_PASSWORD=changeme` → API may work but is unacceptable for any demo. Use `openssl rand -base64 24`.
- `deploy/.env` accidentally committed → `git rm --cached deploy/.env && git commit -m "fix: untrack .env"`.

**🛑 STOP gate**: Paste (no secrets):

```text
Phase 4 environment:
  .env mode = <paste ls -la first 10 chars>
  non-comment var count = <paste grep -cE output>
  gitignored = <YES/NO>
  ECE_SERVER_TODAY_ANCHOR format = <YYYY-MM-DD YES/NO>
  POSTGRES_PASSWORD is openssl rand? = <YES/NO>
```

---

## Phase 5 — Start API + Postgres

**Goal**: Bring up the demo compose stack; confirm both services healthy.

**Commands**:

```bash
cd /opt/ece

# Start
docker compose -f deploy/docker-compose.demo.yml --env-file deploy/.env up -d

# Confirm running
docker compose -f deploy/docker-compose.demo.yml ps

# Tail logs if anything is unhealthy
docker compose -f deploy/docker-compose.demo.yml logs api --tail 100
docker compose -f deploy/docker-compose.demo.yml logs db --tail 50
```

**Placeholders**: None — `deploy/.env` (Phase 4) supplies everything.

**Expected output**:
- `docker compose ps` shows two services: `api` (state `Up`, health `(healthy)`), `postgres` (state `Up`, health `(healthy)`).
- `docker compose logs api --tail 100` ends with `Application startup complete` or `Uvicorn running on http://0.0.0.0:8000`.

**Common errors**:
- `Bind for 0.0.0.0:8000 failed: port is already allocated` → another process (or a stray `uvicorn` from a previous test) is bound to port 8000 on the host. `sudo lsof -i :8000` and stop it.
- `postgres` unhealthy → `docker compose logs db --tail 50`; usually `permission denied on /var/lib/postgresql/data` (volume ownership). `docker compose down -v && docker compose up -d` to reset.
- `api` unhealthy: `pg_isready` failed → wait 10 s and re-check `ps`; the `depends_on: condition: service_healthy` should gate this.
- `pgvector/pgvector:pg16` pull fails → confirm outbound HTTPS to Docker Hub (`docker pull pgvector/pgvector:pg16`). If a proxy is required, configure `/etc/systemd/system/docker.service.d/http-proxy.conf` and restart docker.

**🛑 STOP gate**: Paste (no secrets):

```text
Phase 5 compose up:
  api state = <Up/Down> health = <healthy/starting/unhealthy>
  postgres state = <Up/Down> health = <healthy/starting/unhealthy>
  api log tail = <paste last 5 lines>
```

**Do not proceed to Phase 6 until both services are `Up + healthy`.**

---

## Phase 6 — Migration + Seed (in-container; R3-B2 fix)

**Goal**: Run alembic upgrade + three domain seeds **inside** the api container (the postgres port is not exposed on the host — host alembic cannot reach it).

**Commands**:

```bash
cd /opt/ece

# 6.1 — alembic schema migration
docker compose -f deploy/docker-compose.demo.yml exec -T api alembic upgrade head

# 6.2 — procurement fixtures
docker compose -f deploy/docker-compose.demo.yml exec -T api \
    python scripts/seed_v0_spike_fixture.py

# 6.3 — knowledge-management fixtures
docker compose -f deploy/docker-compose.demo.yml exec -T api \
    python scripts/seed_knowledge_fixture.py

# 6.4 — compliance fixtures
docker compose -f deploy/docker-compose.demo.yml exec -T api \
    python scripts/seed_compliance_fixture.py
```

> **Equivalent one-shot**: `bash deploy/scripts/reset-demo-fixtures.sh` does all four steps. Use it for re-runs between demos (Phase 11).

**Placeholders**: None.

**Expected output**:
- 6.1 ends with `Running upgrade  -> <head_revision>` (no errors).
- 6.2 / 6.3 / 6.4 each print `SELF-CHECK PASSED` or equivalent success marker, no tracebacks.

**Common errors**:
- `alembic: command not found` inside the container → the image was built without alembic. Re-run `docker compose build api` or check the Dockerfile includes `alembic` in the venv.
- `connection refused` on 5432 → `postgres` is not yet healthy (Phase 5 STOP gate missed). Wait and retry.
- Seed script fails with `relation "..." does not exist` → alembic didn't actually run. Run 6.1 first.
- Seed script fails with `ModuleNotFoundError` → image was built without the seed scripts mounted; check `deploy/docker-compose.demo.yml` `volumes:` block binds `../scripts` into the container.

**🛑 STOP gate**: Paste (no secrets):

```text
Phase 6 migration + seed:
  alembic upgrade head = <last 3 lines of output>
  procurement seed = <last 3 lines>
  knowledge seed = <last 3 lines>
  compliance seed = <last 3 lines>
```

---

## Phase 7 — Nginx (enable site; reload)

**Goal**: Install the ECE demo nginx config and serve the SPA at `corln.rana.asia`.

**Commands**:

```bash
# 7.1 — copy config
sudo cp /opt/ece/deploy/nginx/corln.rana.asia.conf /etc/nginx/sites-available/

# 7.2 — enable site
sudo ln -sf /etc/nginx/sites-available/corln.rana.asia.conf /etc/nginx/sites-enabled/

# 7.3 — disable default site (if any) on port 80 to avoid conflict
sudo rm -f /etc/nginx/sites-enabled/default

# 7.4 — syntax check
sudo nginx -t

# 7.5 — reload
sudo systemctl reload nginx

# 7.6 — local health probe (loopback nginx → api)
curl -i http://127.0.0.1/healthz
```

**Placeholders**: None — the config hardcodes `corln.rana.asia` and `/opt/ece/demos/spa`.

**Expected output**:
- `nginx -t` prints `syntax is ok` and `test is successful`.
- `systemctl reload nginx` returns no output, exit 0.
- `curl -i http://127.0.0.1/healthz` returns HTTP/1.1 200 + body (usually `ok` or a JSON status object).

**Common errors**:
- `nginx -t` fails with `unknown directive "gzip_vary"` → old nginx (< 1.18). Re-install nginx from the official nginx repo (`add-apt-repository ppa:nginx/stable`).
- `systemctl reload nginx` → `Job for nginx.service failed` → `journalctl -xeu nginx.service` for the cause (usually a `bind` conflict on port 80 from apache/caddy).
- `curl http://127.0.0.1/healthz` returns 502 → api container not running (re-check Phase 5) OR `127.0.0.1:8000` not bound inside the container. `docker compose exec api ss -tlnp | grep :8000`.
- SPA `/` returns the SPA index.html (HTML, not JSON). If it returns 404, the `root /opt/ece/demos/spa;` line is wrong — verify Phase 3 cloned to `/opt/ece`.

**🛑 STOP gate**: Paste (no secrets):

```text
Phase 7 nginx:
  nginx -t = <paste "syntax is ok" line>
  systemctl reload = <OK / failed: <reason>>
  curl 127.0.0.1/healthz = HTTP <code>, body: <paste first 80 chars>
  curl 127.0.0.1/ (SPA) = HTTP <code>, body starts with: <paste first 40 chars>
```

---

## Phase 8 — HTTPS (certbot --nginx)

**Goal**: Issue a Let's Encrypt cert via HTTP-01 challenge and let certbot patch the nginx config for HTTPS.

**Commands**:

```bash
# 8.1 — run certbot (webroot mode — does NOT need nginx to be down)
sudo certbot --nginx -d corln.rana.asia

# 8.2 — confirm cert issued
sudo certbot certificates

# 8.3 — confirm HTTPS works
curl -fsSI https://corln.rana.asia/healthz
```

**Placeholders**: None — `corln.rana.asia` matches the nginx server_name.

**Expected output**:
- 8.1 prints `Successfully received certificate` + `Certificate is saved at: /etc/letsencrypt/live/corln.rana.asia/fullchain.pem`.
- 8.2 lists the cert with `Expiry Date: <~90 days from now>`.
- 8.3 returns `HTTP/2 200` over TLS.

**Common errors**:
- `Challenge failed for domain corln.rana.asia` → DNS not yet pointing to this server (Phase 1 STOP gate missed) OR port 80 not reachable from Let's Encrypt (firewall / cloud security group).
- `certbot: error: unrecognized arguments: --nginx` → `python3-certbot-nginx` not installed (Phase 2). `sudo apt install -y python3-certbot-nginx`.
- `Rate limit` → too many certs issued for this domain recently. Wait or use the staging server (`--test-cert`).
- `HTTPS works` but HTTP redirects nowhere → that is correct; certbot added a `return 301` to the HTTP block. Verify with `curl -fsSI http://corln.rana.asia/healthz` returning a 301 to `https://`.

**🛑 STOP gate**: Paste (no secrets):

```text
Phase 8 HTTPS:
  certbot --nginx = <Successfully received certificate YES/NO>
  certbot certificates = Expiry Date = <paste>
  curl https://corln.rana.asia/healthz = HTTP <code>
  auto-renewal = <enabled YES/NO>  # sudo certbot renew --dry-run
```

---

## Phase 9 — Real URL same-origin smoke ⭐ COMPLETION GATE

**Goal**: Verify that the deployed `https://corln.rana.asia` produces `PASS=10 SKIP=0 FAIL=0` against the production same-origin deployment smoke. This is the **only** gate that closes cut-045R2.

**Commands**:

```bash
cd /opt/ece

# 9.1 — ensure the api image has the smoke script
docker compose -f deploy/docker-compose.demo.yml exec -T api \
    python -c "import os; assert os.path.exists('scripts/cut_045_demo_deployment_smoke.py'), 'smoke missing in image'"

# 9.2 — run the smoke against the public URL
DEMO_BASE_URL=https://corln.rana.asia \
    docker compose -f deploy/docker-compose.demo.yml exec -T api \
    python scripts/cut_045_demo_deployment_smoke.py

# 9.3 — alternatively, run from host if Python venv available locally
# DEMO_BASE_URL=https://corln.rana.asia .venv/bin/python scripts/cut_045_demo_deployment_smoke.py
```

**Placeholders**: None.

**Expected output (mandatory for cut-045R2 closure)**:

```text
[cut-045 deployment smoke] DEMO_BASE_URL=https://corln.rana.asia

[PASS] 1. SPA index.html reachable from origin (proxy proof)
[PASS] 2. /api/v1/demo/domains lists procurement + knowledge + compliance
[PASS] 3. procurement valid (spike-user-procurement → auto_approved|review_required)
[PASS] 4. procurement denied (spike-user-unrelated → no_permission)
[PASS] 5. knowledge valid (km-alice + KM-POL-001 → answerable)
[PASS] 6. knowledge denied (km-eve + KM-POL-001 → no_permission)
[PASS] 7. compliance valid (comp-alice + COMP-CTL-001 + period → evidence_package_sufficient)
[PASS] 8. compliance denied (comp-eve + COMP-CTL-001 + period → no_permission)
[PASS] 9. 422 strict date (compliance today='not-a-date' → 422)
[PASS] 10. zero external CDN (SPA serves static only)

PASS=10 SKIP=0 FAIL=0
```

**Common errors**:
- `PASS=8 SKIP=2 FAIL=0` → SPA checks (1 + 10) SKIPPED. This means the origin is **API-only** (uvicorn), not the nginx reverse proxy. Re-check Phase 7 STOP gate (curl `/` returned HTML not JSON).
- `FAIL: procurement valid returns 401 / no_permission` → seed not run (Phase 6 STOP gate missed) or seed used the wrong actor (`proc-alice` instead of `spike-user-procurement`).
- `FAIL: compliance valid returns 422 on a valid period` → `ECE_SERVER_TODAY_ANCHOR` (Phase 4) is malformed. Must be strict `YYYY-MM-DD`.
- `FAIL: zero external CDN` → someone added `<script src="https://...">` to the SPA. Check `demos/spa/index.html`.

**🛑 STOP gate — MANDATORY**:

```text
Phase 9 REAL URL SMOKE (cut-045R2 closure gate):
  DEMO_BASE_URL = https://corln.rana.asia
  result = PASS=10 SKIP=0 FAIL=0
  full output = <paste complete smoke output below>
```

**Without `PASS=10 SKIP=0 FAIL=0` from a real `https://corln.rana.asia` URL, cut-045R2 CANNOT close.** Re-run Phase 6 / 7 / 8 until the smoke passes.

---

## Phase 10 — Manual View A / B / C validation

**Goal**: Open the SPA in a browser and verify the three views render correctly with business language (no internal technical tokens leak).

**Commands**:

```bash
# 10.1 — open the demo in a browser
xdg-open https://corln.rana.asia 2>/dev/null \
    || open https://corln.rana.asia 2>/dev/null \
    || echo "open https://corln.rana.asia in your browser manually"

# 10.2 — View C business-language check (server-side grep)
curl -fsS https://corln.rana.asia/ \
    | grep -nE 'ctx\.|decision_id|policy_id|evidence_id|input_context_ref|package_id|context_request_id' \
    || echo "View A/B/C: NO internal tokens leaked (PASS)"

# 10.3 — zero external CDN check (server-side grep)
curl -fsS https://corln.rana.asia/ \
    | grep -nE 'src="https?://|href="https?://' \
    || echo "Zero external CDN (PASS)"
```

**Placeholders**: None.

**Expected output**:
- Browser shows: View A (three domain cards: procurement / knowledge / compliance), View B (kernel perspective, 5 blocks), View C (blueprint with status badges).
- 10.2 prints `NO internal tokens leaked (PASS)`.
- 10.3 prints `Zero external CDN (PASS)`.

**Manual checks (browser)**:

| View | Check | Pass criterion |
|---|---|---|
| A | Procurement valid case | `auto_approved` or `review_required` (not `no_permission`) |
| A | Procurement denied case | `no_permission` |
| A | Knowledge valid case | `answerable` with ≥ 1 evidence |
| A | Knowledge denied case | `no_permission` |
| A | Compliance valid case | `evidence_package_sufficient` |
| A | Compliance denied case | `no_permission` |
| B | Five kernel blocks | All five expand and explain the latest decision |
| C | Three domain pack badges | 采购 ✅ / 知识管理 ✅ / 企业合规 ✅ |
| C | Same-origin Deployment | 🔨 (NOT ✅ — only config-as-code done so far; real-deployed-status flips to ✅ when Phase 9 PASS=10 SKIP=0) |
| C | Customer Private Deployment | ⬜ 规划中 (must remain ⬜) |
| C | Evolution roadmap | All 6 nodes visible |

**Common errors**:
- View A click on procurement card shows blank → `https://corln.rana.asia/api/v1/demo/run` 404 → nginx `/api/` proxy misconfigured. Re-check Phase 7.
- View C shows `Same-origin Deployment ✅` in the browser but `🔨` in the SPA source → view C HTML was edited manually; restore from `demos/spa/index.html` and rebuild / re-pull.
- `decision_id` shows up in View C → business language regression; check `demos/spa/app.js` for the `decision_id` literal.

**🛑 STOP gate**: Paste:

```text
Phase 10 manual validation:
  View A 6 cases = <paste observed conclusion for each>
  View B 5 blocks = <all 5 render YES/NO>
  View C badges = <paste badge state for Same-origin / Customer Private>
  10.2 grep = <NO internal tokens leaked YES/NO>
  10.3 grep = <Zero external CDN YES/NO>
```

---

## Phase 11 — Demo reset (between demo sessions)

**Goal**: Provide a one-shot reset for use between customer demos. Idempotent — safe to re-run anytime.

**Commands**:

```bash
cd /opt/ece
bash deploy/scripts/reset-demo-fixtures.sh
```

**Placeholders**: None.

**Expected output**:
- 4 steps run, each ending with success markers:
  - `alembic upgrade head` → `Running upgrade ... -> <head>`
  - 3 seed scripts → `SELF-CHECK PASSED` (or equivalent success marker)

**Common errors**:
- `FATAL: api service is not running` → Phase 5 stack died. `docker compose -f deploy/docker-compose.demo.yml ps` and restart.
- `FATAL: api container has no DATABASE_URL set` → `deploy/.env` not mounted. Re-check Phase 4 + `docker-compose.demo.yml` `env_file:` directive.
- Seed script `ModuleNotFoundError` → image was rebuilt without the seed scripts mounted; check `deploy/docker-compose.demo.yml` `volumes:` block.

**🛑 STOP gate**: This phase is **optional** — paste only if you ran it:

```text
Phase 11 reset:
  alembic = <last line>
  procurement = <last line>
  knowledge = <last line>
  compliance = <last line>
```

---

## Phase 12 — Rollback / troubleshooting

This phase is **reference only** — there is no STOP gate. Use it when something goes wrong.

### 12.1 API unhealthy

```bash
docker compose -f deploy/docker-compose.demo.yml logs api --tail 200
docker compose -f deploy/docker-compose.demo.yml ps api
# Common fix: dependency wait; restart
docker compose -f deploy/docker-compose.demo.yml restart api
```

### 12.2 Postgres unhealthy

```bash
docker compose -f deploy/docker-compose.demo.yml logs db --tail 200
docker compose -f deploy/docker-compose.demo.yml ps db
# If volume corrupted (rare): reset (LOSES DEMO DATA)
docker compose -f deploy/docker-compose.demo.yml down -v
docker compose -f deploy/docker-compose.demo.yml up -d
bash deploy/scripts/reset-demo-fixtures.sh
```

### 12.3 nginx 502

```bash
# Is api bound to loopback?
docker compose -f deploy/docker-compose.demo.yml exec api ss -tlnp | grep :8000
# nginx upstream syntax
sudo nginx -t
# nginx error log
sudo tail -100 /var/log/nginx/error.log
```

Most common cause: api container restarted but loopback bind not re-established (Phase 5 topology drift). `docker compose restart api` then re-test.

### 12.4 DNS not resolving

```bash
dig +short corln.rana.asia A
# If empty: re-add A record at registrar
# If wrong IP: edit A record
```

### 12.5 certbot failed

```bash
sudo certbot certificates
sudo certbot renew --dry-run
# Most common: port 80 blocked → open inbound 80 in firewall
```

### 12.6 Smoke `no_permission` for valid user

```bash
# Seed not loaded
docker compose -f deploy/docker-compose.demo.yml exec api \
    python scripts/seed_v0_spike_fixture.py
docker compose -f deploy/docker-compose.demo.yml exec api \
    python scripts/seed_knowledge_fixture.py
docker compose -f deploy/docker-compose.demo.yml exec api \
    python scripts/seed_compliance_fixture.py
```

### 12.7 Smoke 422 on valid period

```bash
# ECE_SERVER_TODAY_ANCHOR malformed
grep ^ECE_SERVER_TODAY_ANCHOR deploy/.env
# Must be strict YYYY-MM-DD, no time component
```

### 12.8 Fixture data polluted by demo

```bash
bash deploy/scripts/reset-demo-fixtures.sh
```

### 12.9 Need to wipe all demo data

```bash
# Stops stack AND deletes the postgres volume (irreversible)
docker compose -f deploy/docker-compose.demo.yml down -v
docker compose -f deploy/docker-compose.demo.yml up -d
bash deploy/scripts/reset-demo-fixtures.sh
```

### 12.10 Need to roll back to a previous commit

```bash
cd /opt/ece
git fetch
git log --oneline -20     # find the previous known-good commit
git checkout <known-good-commit>
docker compose -f deploy/docker-compose.demo.yml build api
docker compose -f deploy/docker-compose.demo.yml up -d
bash deploy/scripts/reset-demo-fixtures.sh
# Re-validate with Phase 9 smoke
```

---

## Appendix A — Cross-reference to deploy/ files

| This checklist step | Uses file | Path |
|---|---|---|
| Phase 3 | ece repo | <https://github.com/cscoheru/ece> (clone to `/opt/ece`) |
| Phase 4 | env template | `deploy/.env.example` |
| Phase 5 / 6 / 11 | compose stack | `deploy/docker-compose.demo.yml` |
| Phase 6 / 11 | seed script | `deploy/scripts/reset-demo-fixtures.sh` |
| Phase 7 | nginx config | `deploy/nginx/corln.rana.asia.conf` |
| Phase 9 | smoke | `scripts/cut_045_demo_deployment_smoke.py` |
| Reference | runbook overview | `deploy/README.md` (11-section narrative companion; this CHECKLIST is the strict 12-phase deploy companion) |

## Appendix B — Cut-045R2 verification gate (Codex sign-off criteria)

For cut-045R2 to close and for Codex to issue final PASS:

- [ ] Phase 9 STOP gate shows `PASS=10 SKIP=0 FAIL=0` against `https://corln.rana.asia`
- [ ] Phase 10 manual validation shows View A 6 cases correct, View B 5 blocks render, View C badges consistent (`Same-origin Deployment` 🔨 flips to ✅ ONLY after Phase 9 PASS=10 SKIP=0; `Customer Private Deployment` stays ⬜)
- [ ] No secrets leaked in any STOP gate paste
- [ ] No external CDN in SPA (10.3 grep clean)
- [ ] No internal token leak in View A/B/C (10.2 grep clean)

When all boxes are checked, paste the Phase 9 + Phase 10 STOP outputs to the cut-045R2 closure memory.

## Appendix C — State model discipline (cut-045R2 closure)

```text
CUT-045 TERMINAL: NO CUT-046.
Only cut-045R* rework cycles are allowed.
Next step after Codex PASS is operational closure / customer material,
not a new implementation cut.
```

If a future defect appears, open `cut-045R3` (or higher R-number). Do not propose `cut-046` or any new implementation cut — that violates the cut-045 terminal scope.