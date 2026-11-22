# ASAP: going live with peerview.it

The actions that stand between today and peerview.it selling credit through Paddle ([ADR 0026](../adr/0026-credit-and-paddle.md)), under one brand ([ADR 0027](../adr/0027-brand-peerview-it.md)). Do them in this order; each is a GitHub issue in the milestone [Go live](https://github.com/jaateixeira/peerview.it/milestone/1). The details for Paddle are in [paddle-application.md](paddle-application.md). Last updated 2026-11-21.

## Now: the brand and the site

| # | Action | Issue | Done when |
|---|---|---|---|
| 1 | Rename the GitHub repository to `peerview.it` (Settings → General), then merge the rename pull request | [#32](https://github.com/jaateixeira/peerview.it/issues/32) | The repository is `jaateixeira/peerview.it` and the rename PR is merged |
| 2 | Check the trade mark registers for "peerview" (EUIPO eSearch / TMview, PRH; classes 9, 41, 42) | [#33](https://github.com/jaateixeira/peerview.it/issues/33) | No conflicting mark, or a decision taken |
| 3 | Deploy main to the server: one `sed` on the systemd unit for the new package name, migrations 0015 and 0016 | [#34](https://github.com/jaateixeira/peerview.it/issues/34) | `/pricing`, `/terms`, `/refunds`, `/privacy`, `/contact` answer on https://peerview.it |

## This week: the seller and the pages

| # | Action | Issue | Done when |
|---|---|---|---|
| 4 | Decide how to sell, yourself or as a toiminimi (ask an accountant or Verohallinto), and open the payout bank account | [#35](https://github.com/jaateixeira/peerview.it/issues/35) | Legal name, address and bank account known |
| 5 | Fill in `[seller]`: legal name, address, email, phone, processors | [#36](https://github.com/jaateixeira/peerview.it/issues/36) | No "not set" on the five pages |
| 6 | Make the privacy notice true: log retention (90 days) and the list of processors (Brevo, Cloudflare if used, hosting) | [#37](https://github.com/jaateixeira/peerview.it/issues/37) | Every sentence of `/privacy` is true |
| 7 | Have the terms, refund policy and privacy notice reviewed (Finnish consumer law, GDPR) | [#38](https://github.com/jaateixeira/peerview.it/issues/38) | Changes from the review are in |

## Then: Paddle

| # | Action | Issue | Done when |
|---|---|---|---|
| 8 | Sandbox: product, three EUR prices, token, notification destination, default payment link, `[paddle]` and the AI keys file; buy, spend and refund test credit | [#39](https://github.com/jaateixeira/peerview.it/issues/39) | Credit comes and goes on `/credit` |
| 9 | Live account: identity verification and website approval of `peerview.it` | [#40](https://github.com/jaateixeira/peerview.it/issues/40) | Paddle approves the domain |
| 10 | Go live: production settings; buy €5 yourself, use it, refund it | [#41](https://github.com/jaateixeira/peerview.it/issues/41) | A real purchase and refund work end to end |

## When there is time

| # | Action | Issue | Done when |
|---|---|---|---|
| 11 | Free AI models: Ollama on the BC-250, `[ai] ollama_url` | [#42](https://github.com/jaateixeira/peerview.it/issues/42) | The pricing page offers free models |

The old name still appears on the server (`/opt/previewit`, the `previewit` unit and account). That is fine: nobody sees it, and ADR 0027 lists what to rename when convenient.
