# 0021. The hosted site lives at peerview.it; peereview.it leads to it

Status: accepted. The product name and the repository name are superseded by [ADR 0027](0027-brand-peerview-it.md): the product is now peerview.it

## Context
The product is called Previewit, but `preview.it` belongs to someone else. The docs and the repository used three spellings for the address, and the business docs listed the name as an open question. The founder registered **`peereview.it`** (2026-11-14) and **`peerview.it`** (2026-11-15), both renewed yearly. `peereview.it` reads as "peer review it" but has to be spelled aloud; `peerview.it` is typed as it is heard.

## Decision
- **One site, one main address, any number of aliases.** `[server] base_url` is the main address. `[server] aliases` lists other addresses of the same site. A request that arrives under an alias is redirected (308) to the same page at the main address, before anything else runs.
- **Why redirect and not serve both.** Forms are checked against one origin, cookies belong to one host, and Google, Apple and HAKA each return to one registered address. One origin keeps all of that simple and safe; no page or link is ever built from the name in a request.
- **`peerview.it` is the main address and `peereview.it` is an alias** (founder's choice, 2026-11-15): the main name must survive being said aloud. Which name is main is configuration, not code. Later names, such as `peerview.jteixeira.eu`, are added as aliases; a path on another site, such as `jteixeira.eu/peerview`, is redirected by that site's own server.
- ~~**The product name stays Previewit.**~~ *Superseded by ADR 0027: the product is peerview.it.* The page footer shows the main address beside the name, read from `base_url` (`Settings.host`), so a self-hosted site shows its own.
- **Placeholders use `peerview.example` and `peereview.example`** in the example configuration and in tests. `.example` is reserved, so nothing can reach a real site by mistake.
- ~~**The GitHub repository keeps its name** (`jaateixeira/prreview.it`) for now. Renaming it is the owner's choice; GitHub redirects the old name.~~ *Superseded by ADR 0027: it becomes `jaateixeira/peerview.it`.*

## Consequences
- Both names must reach the server (DNS and the proxy or tunnel), and each needs a certificate. Hosts that are neither the main address nor an alias are served as before, so the health check on `127.0.0.1` keeps working.
- A form posted to an alias is moved, not processed; the browser then shows the form again at the main address. Links in emails always use the main address.
- Mail goes out from an address at the main domain; that domain needs SPF, DKIM and DMARC records before the first invitation is sent.
- HAKA registration (ADR 0007) names the entity ID at the main address, `https://peerview.it/saml/sp`. Changing the main address later means registering again with each login provider.
- "PeerView" is used as a name by other companies. It is an address here, not the product name; check the EU trade mark register before building a brand on the word. *ADR 0027 makes it the brand: that check is now one of the first actions.*
- A `.it` name must keep two working name servers and correct holder details, and it must be renewed each year.
