# 0021. The hosted site lives at peereview.it

Status: accepted

## Context
The product is called Previewit, but `preview.it` belongs to someone else. The docs and the repository used three spellings for the address (`peereview.it`, `prreview.it`, `peerreview.it`), and the business docs listed the name as an open question. The founder registered **`peereview.it`** on 2026-11-14 (yearly renewal).

## Decision
- **The hosted site is `https://peereview.it`.** Read it as "peer review it": *peer*, then *eview*, one `r` in the middle. Docs, examples and mail use this one spelling.
- **The product name stays Previewit.** The page footer shows the site address beside the name. It is read from `base_url` (`Settings.host`), so a self-hosted site shows its own address and no domain is hard-coded.
- **Placeholders use `peereview.example`** in the example configuration and in tests. `.example` is reserved, so nothing can be sent to a real site by mistake.
- **The GitHub repository keeps its name** (`jaateixeira/prreview.it`) for now. Links to it stay as they are. Renaming it is the owner's choice; GitHub redirects the old name.

## Consequences
- Said aloud, people may type `peerreview.it` (two r's), which is a different name. Print the link, and write it `peeReview.it` where capitals help.
- Mail will go out from an address at `peereview.it`; the domain needs SPF, DKIM and DMARC records before the first invitation is sent.
- HAKA registration (ADR 0007) can now name the real entity ID, `https://peereview.it/saml/sp`.
- A `.it` name must keep two working name servers and correct holder details, and it must be renewed each year.
