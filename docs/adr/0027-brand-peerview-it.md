# 0027. The brand is peerview.it, everywhere

Status: accepted (2026-11-21). Supersedes the product name and repository name in [ADR 0021](0021-site-addresses.md).

## Context
The product grew up as **Previewit**, in a repository called `prreview.it`, served at `peerview.it` (ADR 0021). Three names for one thing confuse buyers, reviewers and Paddle's website review (ADR 0026), which compares the seller's site, terms and product. The founder decided on 2026-11-21: **peerview.it is the brand**, in code, documents and plans.

## Decision
- **How to write it:** `peerview.it`, all lowercase, also at the start of a sentence and in titles. Possessive: *peerview.it's*. Never *Previewit*, *PeerView*, *Peerview* or *Peer View*.
- **Where it can't have a dot**, the name is `peerview`: the Python package (`src/peerview`), its distribution, the plugin entry-point group `peerview.plugins`, settings `PEERVIEW_*`, the config file `/etc/peerview/peerview.toml` (and `peerview.example.toml`), the service account, database and systemd unit in the deployment manual, the cache namespace. User agents are `peerview.it-page-check/1.0` and `peerview.it-ai-review/1.0`.
- **The repository** becomes `jaateixeira/peerview.it`. GitHub forwards the old address. The owner renames it in GitHub's settings (Settings → General → Repository name); every link in the repository already uses the new name.
- **Kept on purpose:**
  - the session signing salt still says `previewit-session`, because changing it would sign everyone out;
  - the cookies stay `pv_*`, which fits both names.
- **Old setting names keep working until the end of 2027:**
  - `PREVIEWIT_*` variables count as `PEERVIEW_*` unless the new name is set too;
  - `previewit.toml` and `/etc/previewit/previewit.toml` are still found.

  Each logs a warning at start.
- **Enforced:** `tests/unit/test_vocabulary.py` fails on the old name or a wrong spelling anywhere in code, tests, docs and scripts. The only exceptions are this ADR, ADR 0021 (a record of what was decided then), the glossary, the action list, and the two places that keep old settings working.

## Moving a running server
The Python package's name changed, so the systemd unit must change when this version is deployed. Nothing else must:

```bash
cd /opt/previewit/app            # wherever the server's checkout is
sudo -u previewit git pull
sudo -u previewit /opt/previewit/.local/bin/uv sync --frozen --no-dev --extra postgres --extra valkey
sudo sed -i 's/previewit\.bootstrap/peerview.bootstrap/; s/previewit\.adapters/peerview.adapters/g' \
  /etc/systemd/system/previewit.service
sudo systemctl daemon-reload && sudo systemctl restart previewit
journalctl -u previewit -n 50     # warnings name the old settings still in use
```

When convenient:
- rename the `PREVIEWIT_*` variables in the unit to `PEERVIEW_*`;
- move `/etc/previewit/previewit.toml` to `/etc/peerview/peerview.toml`, fixing the secret file paths inside it;
- point the checkout at `https://github.com/jaateixeira/peerview.it`.

The service account, the database and the unit's own name may keep the old name: nobody sees them.

## Consequences
- One name on the site, in emails, in Paddle's review and in the code.
- Third-party plugins register under `peerview.plugins`. There are none yet.
- A developer's SQLite file is now `peerview.db`, so old local data stays in `previewit.db`.
- **Trade mark.** ADR 0021 warned that "PeerView" is used as a name by other companies. Before investing in the brand, the founder checks the EU and Finnish trade mark registers (EUIPO eSearch / TMview, PRH) in the classes for software and online services (9, 41 and 42). If there is a conflict, the brand can still change cheaply now.
- Remove the old-name fallbacks in the first release of 2028.
