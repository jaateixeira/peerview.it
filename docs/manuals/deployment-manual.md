# Deployment manual

**Read first.** Self-hosting is for experts and is unsupported ([ADR 0005](../adr/0005-hosted-first-debian-only.md)). The easy path is the hosted site. There is no installer, no container image and no support for other systems.

**Status.** The application has sign-in (email and password, Google, Apple, HAKA), email verification, organizations, spaces, calls, submissions (text and PDF), rounds, reviews and invitations. Outgoing mail, the database and the cache are configurable. Quotas, payment and LTI are not built yet.

**Tested (2026-11-15):** the test suite on Python 3.13 with SQLite and PostgreSQL 16; the configuration file, the migration command and the start command against PostgreSQL 16. **Not tested:** the systemd unit, the nginx configuration and a real Debian 13 host (treat them as an outline to adapt), live Google, Apple, HAKA or SMTP, Valkey itself.

## 1. Requirements

| Item | Requirement |
|---|---|
| Operating system | Debian stable (13). Nothing else. |
| Python | Debian's `python3` (project needs 3.12 or newer) |
| Tools | `git`, `curl`, `uv` |
| Database | PostgreSQL. SQLite is for development only. |
| Cache | Valkey (recommended, optional): keeps the signed-in user close at hand. Required if you run more than one worker. |
| Front | nginx with TLS, or a tunnel that ends TLS and forwards to `127.0.0.1:8000` |
| Email | An SMTP relay. The application does not start on an https address without one. |
| Hardware | Provisional: 4 CPU cores, 8 GB RAM, SSD storage. No load tests exist yet; figures will be set in M7. |
| Skills | Linux administration, systemd, nginx and TLS, PostgreSQL backup and restore, DNS, security patching |

## 2. Runtime view

```mermaid
flowchart LR
    U(["Browser"])
    M(["Moodle, LTI 1.3 (M9)"])
    subgraph srv ["Debian stable server"]
        N["nginx or tunnel: TLS"]
        A["previewit: uvicorn under systemd, 127.0.0.1:8000"]
        P[("PostgreSQL: data and uploaded files")]
        V[("Valkey: cached users, 60 s")]
    end
    SMTP(["SMTP relay"])
    IDP(["Google, Apple, HAKA"])
    U -- HTTPS --> N
    M -. LTI launch .-> N
    N -- HTTP --> A
    A --> P
    A -. optional .-> V
    A --> SMTP
    A --> IDP
```

Valkey is a copy, never the source of truth. If it is down the site is slower, not broken.

## 3. Install

```bash
sudo apt-get update
sudo apt-get install -y python3 git curl ca-certificates postgresql valkey
sudo adduser --system --group --home /opt/previewit previewit
sudo -u previewit -H sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
sudo -u previewit -H git clone https://github.com/jaateixeira/prreview.it /opt/previewit/app
cd /opt/previewit/app
sudo -u previewit -H env UV_PYTHON_PREFERENCE=only-system \
  /opt/previewit/.local/bin/uv sync --frozen --no-dev --extra postgres --extra valkey
```

`--frozen` installs exactly what `uv.lock` pins; `--no-dev` leaves out test tools. Add `--extra saml` for HAKA (needs `xmlsec1` from apt). If `apt` has no `valkey` package on your release, use another Redis-compatible server, or leave the cache out and run one worker. Bind it to `127.0.0.1` and set a password if anything else can reach it.

## 4. Database

```bash
sudo -u postgres createuser --pwprompt previewit
sudo -u postgres createdb --owner previewit previewit
```

## 5. Configure

Settings come from a TOML file and from `PREVIEWIT_*` environment variables; a variable overrides the file. The file is read from `PREVIEWIT_CONFIG`, else `./previewit.toml`, else `/etc/previewit/previewit.toml`.

```bash
sudo install -d -o previewit -g previewit -m 700 /etc/previewit
sudo install -o previewit -g previewit -m 600 previewit.example.toml /etc/previewit/previewit.toml
openssl rand -hex 32 | sudo install -o previewit -g previewit -m 600 /dev/stdin /etc/previewit/secret.key
sudoedit /etc/previewit/previewit.toml
```

Set at least these:

```toml
[server]
base_url = "https://review.example.org"   # exactly the address people type; no trailing slash
secret_key_file = "secret.key"
# aliases = ["https://www.review.example.org"]   # other names of this site (ADR 0021)

[database]
url = "postgresql+psycopg://previewit:PASSWORD@localhost/previewit"

[mail]
smtp_host = "smtp.example.org"
smtp_port = 587
smtp_user = "…"
smtp_password = "…"
smtp_security = "starttls"                 # or "ssl" for port 465
from = "Previewit <no-reply@review.example.org>"

[cache]
url = "valkey://127.0.0.1:6379/0"
```

| Other section | What it sets |
|---|---|
| `[logging]` | `level`: `TRACE`, `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `[policy]` | `require_verified_email_for`: which actions need a verified email. Default: none, so invited reviewers can review without an account and join afterwards (ADR 0020). Listing `review` or `join` turns that off |
| `[login.google]`, `[login.apple]`, `[login.haka]` | providers, each on when configured ([`docs/auth/login-setup.md`](../auth/login-setup.md)) |

The file holds secrets: keep it readable by the `previewit` account only (the server warns if group or others can read it). Typos in keys, sections or action names stop the server at start and name the setting. Forms are checked against `base_url`, so the site lives at that one address. List every other name that reaches the server under `aliases`: visitors who arrive there are sent to the same page at `base_url`. Each name needs DNS, a certificate and a place in the proxy (`server_name`) or tunnel.

## 6. Run

`/etc/systemd/system/previewit.service`:

```ini
[Unit]
Description=Previewit
After=network.target postgresql.service valkey.service

[Service]
User=previewit
Group=previewit
WorkingDirectory=/opt/previewit/app
ExecStartPre=/opt/previewit/app/.venv/bin/python -c "import os; from previewit.adapters.settings import load_settings; from previewit.adapters.persistence.migrate import upgrade; upgrade(load_settings(os.environ).database_url)"
ExecStart=/opt/previewit/app/.venv/bin/uvicorn previewit.bootstrap:create_app --factory --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
```

`ExecStartPre` brings the database to the latest schema before each start; PostgreSQL is never migrated by the application itself. Two workers need the `[cache]` url; without Valkey, remove `--workers 2`, or each worker keeps its own cache and the server warns at start.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now previewit
curl -s http://127.0.0.1:8000/healthz    # prints: ok
journalctl -u previewit -n 50            # if it does not
```

**Logs and console.** On start the service prints a summary (address, database kind, cache, mail, login methods, artifact types, policy; never a secret). Logs go to stderr, so `journalctl -u previewit -f` shows them. For debugging set `[logging] level = "DEBUG"`, or `TRACE` to see every cache hit and miss, and restart.

## 7. Front: TLS and reverse proxy

**nginx.** `/etc/nginx/sites-available/previewit` (link it into `sites-enabled`):

```nginx
server {
    listen 80;
    server_name review.example.org;
    client_max_body_size 12m;     # PDF submissions: 10 MB file plus form fields

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d review.example.org
```

The application also refuses bodies announcing more than 12 MB, but only the proxy can stop a request that does not announce its size, so keep `client_max_body_size`.

**Tunnel.** A tunnel that ends TLS at its provider (for example `cloudflared`) can replace nginx: point its public hostname at `http://127.0.0.1:8000`. It must run on the same host, or `--forwarded-allow-ips` must name the address it connects from.

## 8. Outgoing email

Previewit sends verification mails and invitations over SMTP only. Use a relay that signs for your domain, and publish its SPF, DKIM and DMARC records before the first invitation. Send yourself an invitation and check that the headers say `spf=pass` and `dkim=pass`.

## 9. Backup

Submitted text and PDFs are stored **in PostgreSQL** (table `revisions`), so a database backup is the whole backup: dump regularly and test a restore. Valkey needs no backup; it only holds copies. Keep the configuration and the secret key with the dumps: with a new key, everyone is signed out.

```bash
sudo -u postgres pg_dump --format=custom previewit > previewit-$(date +%F).dump
sudo -u postgres pg_restore --clean --dbname previewit previewit-2026-11-15.dump
```

## 10. Update

```bash
cd /opt/previewit/app
sudo -u previewit -H git pull --ff-only
sudo -u previewit -H env UV_PYTHON_PREFERENCE=only-system \
  /opt/previewit/.local/bin/uv sync --frozen --no-dev --extra postgres --extra valkey
sudo systemctl restart previewit         # migrates, then starts
```

Take a dump first. Read the release notes; the plugin API is unstable until version 0.2.

## 11. Planned sections

| Topic | Milestone |
|---|---|
| Monitoring, logs, performance budgets | M7 |
| Quotas and payment (hosted mode only), separate file storage | M8 |
| LTI 1.3 registration in Moodle | M9 |

## 12. Licence duties

Previewit is AGPL-3.0-or-later. If you run a modified version for others over a network, you must offer them your source. The page footer links to `SOURCE_URL` in `src/previewit/adapters/web/app.py`; point it at your own repository if you change the code.
