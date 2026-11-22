# 0019. Local time and due dates

Status: accepted

## Context
Every moment was typed and shown in UTC ("Closes (UTC, optional)"). A teacher in Finland who wants reviews by four in the afternoon had to type 14:00 in winter and 13:00 in summer. The due-date picker also offered days in the past, and a date without a time became 23:59 UTC. The product owner asked for three things: the calendar starts today, reviews are due at 16:00 by default and the time can be changed, and a note that a paid plan chooses when peerview.it sends reminders.

## Decision
- **Stored in UTC, typed and shown in the viewer's zone.** A small script (`static/js/local-time.js`) puts the browser's IANA time zone in the `pv_tz` cookie. `adapters/web/local_time.py` converts input to UTC and output to local time, with the zone's abbreviation ("2027-06-01 16:00 EEST"). Without the cookie (first request, no JavaScript) everything is UTC and says so. An unknown or malformed zone name falls back to UTC. The domain and application layers stay in UTC.
- **"Reviews due" is a day plus a time.** The round form and the request-a-review page ask for a day (a date picker whose `min` is today in the viewer's zone) and a time that defaults to 16:00. A Round still has one `closes_at`; the form only reads it in two parts.
- **The past is refused where a person types it.** The request-a-review service refuses a due time that has passed. The round form refuses a new or changed due time that has passed, but saves an unchanged earlier one so a closed round can still be edited. The picker keeps an earlier saved day as its `min` for the same reason.
- **Default due date.** Request-a-review without a day: two weeks from today in the organizer's zone, at 16:00 (or the time typed). The service computes it with its own clock.
- **Reminders are a paid feature.** The note "Join a paid plan to choose when peerview.it sends reminders" is shown beside the due date. Reminders are not built; when they are (M8), the choice goes through the `Entitlements` port.
- **Local address.** `make run` and the macOS scripts serve and open `http://localhost:8000`, the default base URL, so form posts pass the Origin check. A refused form now says where peerview.it runs, and the reason is logged.

## Consequences
- A call deadline is also typed and shown in local time. The call deadline picker does not limit days; that is for a later change.
- Two people in different zones see the same moment in their own clocks. E-mails still render times in UTC; that is for a later change.
- Tests: unit tests for parsing and zones (including a round-trip property), web tests for the 16:00 default and the refusal of a past due day, and a browser scenario in the Europe/Helsinki zone.
