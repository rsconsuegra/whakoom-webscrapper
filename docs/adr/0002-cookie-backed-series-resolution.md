# ADR-0002 — Cookie-backed (login) resolution for list → series

- **Status:** Accepted
- **Date:** 2026-08-01
- **Supersedes:** (none)

## Context

List items expose only a volume URL and slug (`/comics/{volume_slug}/{series_slug}/{number}`). The
series page URL needs the numeric `title_id` (`/ediciones/{title_id}/{series_slug}`). That id is
exposed only on gated pages:

- `/comics/...` redirects **every** client (even Googlebot) to `/login` and is `robots.txt`-disallowed.
- `/search` and `/pwkws.asmx/QuickView` return 401 for anonymous clients.
- `robots.txt` disallows `/comics/`, `/search`, `/ediciones/.../todos`.

There is no anonymous path from a volume slug to the series id.

## Decision

Accept a logged-in session for the **resolution step only**, via an imported cookie jar:

- The owner logs into Whakoom once in a browser and exports the session cookies to
  `WHAKOOM_COOKIE_FILE` (Netscape format).
- `http/session.py` loads the jar; the resolver uses it for the gated endpoints.
- Resolution is the **only** gated step; the bulk scraping (lists index, list detail + pagination,
  series/ediciones pages, publishers, authors) runs on public, robots-allowed pages.
- One request per unique series slug (never more).
- The robots policy treats gated requests as an explicit exception gated behind
  `WK_ALLOW_GATED_RESOLUTION=1`.
- On 401 / redirect-to-login during resolution, the stage **fails loudly** ("session expired — re-export
  cookies") with a resumable pipeline; unresolved slugs are exported to `review_unresolved.csv`.

No automated credential login: the site runs `recaptcha/enterprise.js`, so automated login is fragile.

## Consequences

**Positive:** the entire analytical dataset (rating, votes, distribution, authors, synopsis, volumes)
comes from public pages; the logged-in footprint is minimal (one request per series); the pipeline is
resumable across cookie expirations.

**Negative:** the project depends on a hand-exported cookie file and on a small robots.txt-disallowed
exception. This is a deliberate, owner-approved tradeoff for a single-user, personal/research project
and is documented in the README.

## Alternatives considered

- **No login, derive the series id elsewhere** — rejected: no anonymous source exposes it.
- **Automated credential login** — rejected: recaptcha makes it fragile.
