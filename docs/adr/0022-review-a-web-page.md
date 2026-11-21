# 0022. Review a web page by its address

Status: accepted (widens the year-1 scope of ADR 0005: text, PDF and web pages)

## Context
Much of what people want reviewed already lives on the web: a portfolio, a blog post, a project page, a published draft. Saving it as a PDF to upload loses the thing itself. The founder asked for a base feature: instead of uploading a file, paste the address of a public page; peerview.it checks it can be reached and shows a preview.

Fetching an address a stranger typed is a well-known way to make a server read its own private network (server-side request forgery), so the check must be safe by construction. A page peerview.it does not copy also has no places to pin comments to, and today a PDF reviewed without a rubric leaves reviewers with no way to comment at all.

## Decision
- **A plugin, like text and PDF.** The built-in artifact type `webpage` ("Web page") takes an address (`input_kind = "url"`). It keeps a small record of the check (address, where redirects led, title, description, site name, media type, any note), not the page. Reviewers see a card with the title and an **Open the page** link that opens in a new tab (`rel="noopener noreferrer nofollow"`). Calls can accept web pages, and *Request a review* takes an address next to the file and the text box.
- **The core lends plugins what they need from outside.** A plugin cannot import an adapter, so the composition root gives plugins a `PluginServices` with a `PageChecker` port (`connect_plugins`). A plugin that offers a name for its content implements `NamesItself`; *Request a review* uses it when the title is left empty (a page's title).
- **The address rules** (`normalise_address`, no network): `https://` or `http://` only (`https://` is added when missing); no user name or password; a host with a dot that is not `localhost`, `.local`, `.internal`, `.lan`, `.home.arpa` or `.intranet`; an IP address only if it is public (`is_global`, also inside IPv6 forms); the usual ports only (80, 443); at most 2000 characters.
- **The safe fetch** (`HttpPageChecker`): peerview.it resolves every host itself and connects only to the address it checked, so a name that points into a private network is refused at connect time, also after a redirect and also if the name's answer changes between two lookups. TLS still checks the certificate against the name. At most five redirects, the usual ports only, proxy settings in the environment ignored, a few seconds per step and ten in all. Only the first 256 kB of an HTML page is read, for the title; other content (a PDF, an image) is not downloaded.
- **What a check says.** 2xx: reachable, with a preview. 401: refused ("asks for a login"). 403 and 429: accepted with a note, since such answers are often robot guards that a person gets past. 404/410: not found. 5xx: try later. Unreachable pages are refused with the reason in plain words.
- **Live, but not for strangers.** The form checks the address while it is typed (`POST /pages/check`, HTMX). Only signed-in people can make peerview.it fetch, at most 30 checks a minute each. Successful checks are remembered for five minutes, so the live check and the submit fetch once.
- **Comments on the whole work.** A comment with nothing selected is about the whole work (`Annotation.kind = "whole"`, an empty selector), for every artifact type. Text keeps pinned comments, and a reviewer can unpin a selection. This also gives PDF reviews without a rubric a way to comment.

## Consequences
- The page can change after it was submitted. The card says that peerview.it checked it on submission; the record keeps what the check found. A copy of the page (an archive) is not part of this decision.
- The server needs outbound HTTPS and DNS. The deployment manual says so.
- Year 1 now covers text, PDF and web pages. Other plugins stay out of year 1.
- Glossary: **Web page** (artifact type); **Annotation** now covers comments on the whole work.
