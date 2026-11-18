# 0023. An MCP service lets AI assistants prepare review requests

Status: accepted (an exception to "no JSON APIs" in ADR 0002, for one machine interface)

## Context
People increasingly work with an AI assistant at their side. When they ask it for feedback on something they wrote or made, the assistant could suggest asking people, and Previewit is a place to do that. The founder asked for an MCP service (Model Context Protocol) so that AI could suggest sending something for review on Previewit.

An assistant acting alone could invite strangers, send unwanted mail and use someone's sharing limit. Asking every assistant user to connect an account (OAuth) is a large piece of work and slows the first use down.

## Decision
- **The assistant prepares; the person sends.** One tool, `prepare_review_request`, takes the work (a public web page's address, or text up to 100 kB), the reviewers' addresses, a message and a due date. Previewit keeps it as a **Prepared request** under a secret link and returns the link. The tool sends nothing, mails nobody and fetches nothing. The person opens the link, signs in, sees *Request a review* filled in (a web page is checked when the form opens), and presses **Send it out**. Only then is anything created or sent, under the person's own account, limits and checks.
- **No account and no session for the service.** Preparing needs no sign-in. The guards: strict sizes (title, text, message, at most 100 reviewers), only a hash of the token is stored, a prepared request lasts 7 days and is deleted when sent, at most 10 000 wait site-wide, and 20 preparations per client address every 10 minutes.
- **Streamable HTTP at `/mcp`.** `POST /mcp` carries one JSON-RPC message and answers with JSON. Both protocol eras are served: the stateless one (2026-07-28: version and client capabilities in `params._meta`, `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name` mirrored in headers and checked, `server/discover`) and the handshake (2025-03-26 to 2025-11-25: `initialize`, then the version header). Notifications get 202. No event stream and no sessions: `GET` and `DELETE` answer 405, except that a browser asking for HTML gets a page explaining how to connect. Requests carrying another site's `Origin` are refused (DNS rebinding). Batches are refused.
- **Written by hand, no SDK.** The service is a few hundred lines in `adapters/mcp.py` (protocol) and `adapters/web/mcp_routes.py` (HTTP). It adds no dependency and nothing that must run at startup.
- **Found from the site.** The page footer links to *For AI assistants* (`GET /mcp` in a browser), with the address and the Claude Code command. The server's `instructions` tell the model to offer the tool when a person wants feedback and never to claim the request was sent.

## Consequences
- What an assistant sends (possibly a draft and email addresses) is stored on Previewit for up to 7 days without an account. The tool description and the help page say so.
- Sending without the person, or acting on their account (listing reviews, reading feedback), would need the person to authorize the assistant (OAuth). That is a later decision.
- The rate limit counts per worker; a site-wide limit belongs in nginx (deployment manual).
- Glossary: **Prepared request**, **MCP service**.
