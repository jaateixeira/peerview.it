# Deployment manual

**Read first.** Self-hosting is for experts and is unsupported ([ADR 0005](../adr/0005-hosted-first-debian-only.md)). The easy path is the hosted site. There is no installer, no container image and no support for other systems.

**Status.** The application runs with PostgreSQL, a configuration file, sign-in and outgoing email. Uploaded files are stored in the database.

**Tested (2026-11-15):** the configuration file, the migration command and the start command, against PostgreSQL 16 on Python 3.13. **Not tested:** the systemd unit, the nginx configuration and a real Debian 13 host; treat them as an outline to adapt.

## 1. Requirements

| Item | Requirement |
|---|---|
| Operating system | Debian stable (13). Nothing else. |
| Python | Debian's `python3` (project needs 3.12 or newer) |
| Tools | `git`, `curl`, `uv` |
| Database | PostgreSQL. SQLite is for development only. |
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
    end
    SMTP(["SMTP relay"])
    U -- HTTPS --> N
    M -. LTI launch .-> N
    N -- HTTP --> A
    A --> P
    A --> SMTP
```

Solid lines exist today; dotted lines are planned.

## 3. Install

```bash
sudo apt-get update
sudo apt-get install -y python3 git curl ca-certificates postgresql
sudo adduser --system --group --home /opt/previewit previewit
sudo -u previewit -H sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
sudo -u previewit -H git clone https://github.com/jaateixeira/prreview.it /opt/previewit/app
cd /opt/previewit/app
sudo -u previewit -H env UV_PYTHON_PREFERENCE=only-system \
  /opt/previewit/.local/bin/uv sync --frozen --no-dev --extra postgres
```

`--frozen` installs exactly what `uv.lock` pins; `--no-dev` leaves out test tools. Add `--extra saml` for HAKA login and `--extra valkey` for more than one worker.

## 4. Database

```bash
sudo -u postgres createuser --pwprompt previewit
sudo -u postgres createdb --owner previewit previewit
```

## 5. Configure

```bash
sudo install -d -o root -g previewit -m 750 /etc/previewit
sudo install -o root -g previewit -m 640 previewit.example.toml /etc/previewit/previewit.toml
openssl rand -hex 32 | sudo install -o root -g previewit -m 640 /dev/stdin /etc/previewit/secret.key
sudoedit /etc/previewit/previewit.toml
```

Set at least these. The file explains the rest; login providers are in [`docs/auth/login-setup.md`](../auth/login-setup.md).

```toml
[server]
base_url = "https://review.example.org"   # exactly the address people type; no trailing slash
secret_key_file = "secret.key"

[database]
url = "postgresql+psycopg://previewit:PASSWORD@localhost/previewit"

[mail]
smtp_host = "smtp.example.org"
smtp_port = 587
smtp_user = "…"
smtp_password = "…"
smtp_security = "starttls"                 # or "ssl" for port 465
from = "Previewit <no-reply@review.example.org>"
```

The file holds secrets: keep it readable by `root` and the `previewit` group only. Forms are checked against `base_url`, so the site must be reached under that one address; redirect any other name (such as `www.`) to it.

## 6. Run

`/etc/systemd/system/previewit.service`:

```ini
[Unit]
Description=Previewit
After=network.target postgresql.service

[Service]
User=previewit
Group=previewit
WorkingDirectory=/opt/previewit/app
ExecStartPre=/opt/previewit/app/.venv/bin/python -c "import os; from previewit.adapters.settings import load_settings; from previewit.adapters.persistence.migrate import upgrade; upgrade(load_settings(os.environ).database_url)"
ExecStart=/opt/previewit/app/.venv/bin/uvicorn previewit.bootstrap:create_app --factory --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
```

`ExecStartPre` brings the database to the latest schema before each start; PostgreSQL is never migrated by the application itself. The unit runs one worker. For more, add `--workers N` and configure `[cache]` with Valkey, or each worker keeps its own cache.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now previewit
curl -s http://127.0.0.1:8000/healthz    # prints: ok
journalctl -u previewit -n 50            # if it does not
```

## 7. Front: TLS and reverse proxy

**nginx.** `/etc/nginx/sites-available/previewit` (link it into `sites-enabled`):

```nginx
server {
    listen 80;
    server_name review.example.org;
    client_max_body_size 12m;

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

The application refuses uploads above 12 MB, so the proxy needs no larger limit.

**Tunnel.** A tunnel that ends TLS at its provider (for example `cloudflared`) can replace nginx: point its public hostname at `http://127.0.0.1:8000`. It must run on the same host, or `--forwarded-allow-ips` must name the address it connects from.

## 8. Outgoing email

Previewit sends verification mails and invitations over SMTP only. Use a relay that signs for your domain, and publish its SPF, DKIM and DMARC records before the first invitation. Send yourself an invitation and check that the headers say `spf=pass` and `dkim=pass`.

## 9. Backup

Everything, uploaded files included, is in PostgreSQL. Keep the configuration and the secret key with the dumps: with a new key, everyone is signed out.

```bash
sudo -u postgres pg_dump --format=custom previewit > previewit-$(date +%F).dump
sudo -u postgres pg_restore --clean --dbname previewit previewit-2026-11-15.dump
```

## 10. Update

```bash
cd /opt/previewit/app
sudo -u previewit -H git pull --ff-only
sudo -u previewit -H env UV_PYTHON_PREFERENCE=only-system \
  /opt/previewit/.local/bin/uv sync --frozen --no-dev --extra postgres
sudo systemctl restart previewit         # migrates, then starts
```

Take a dump first. Read the release notes; the plugin API is unstable until version 0.2.

## 11. Planned sections

| Topic | Milestone |
|---|---|
| Monitoring, logs, performance budgets | M7 |
| Quotas and payment (hosted mode only) | M8 |
| LTI 1.3 registration in Moodle | M9 |

## 12. Licence duties

Previewit is AGPL-3.0-or-later. If you run a modified version for others over a network, you must offer them your source. The page footer links to `SOURCE_URL` in `src/previewit/adapters/web/app.py`; point it at your own repository if you change the code.
