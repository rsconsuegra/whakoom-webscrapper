# ADR-0006 — HTTP retry and transient-error contract

- **Status:** Accepted
- **Date:** 2026-08-02
- **Supersedes:** (none)
- **Implements:** V2 §10 (HTTP layer), Phase 2

## Context

Phase 2 built the HTTP layer (`http/session.py`). The plan (V2 §10 and `phases.md` P2) fixed the *intent* —
"retry only on `Timeout`, `ConnectError`, 429, 5xx with exponential backoff; budget `WK_MAX_RETRIES`" — but
left five interoperating details open that every stage depends on:

1. By what **mechanism** does a transient HTTP *status* (429/5xx) trigger a retry? Tenacity retries on
   exceptions by default, not on response objects.
2. What is the **terminal state** when retries are exhausted — return the last 429/5xx response, or raise?
3. Does `WK_MAX_RETRIES` count **total attempts** or **retries on top of the first** attempt?
4. What is the exact **backoff curve**, and where does the **politeness sleep** apply (between distinct
   requests, or before every attempt including retries)?
5. How is the client made **testable** without real waiting and without hitting the network?

## Decision

`WhakoomSession` (in `http/session.py`) implements the following contract:

1. **Exception-driven transient retry.** A 429 or ≥500 response raises
   `TransientRequestError(status_code, url)` inside the request attempt. Tenacity is configured with
   `retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, TransientRequestError))`. Network
   errors already raise; the custom exception is how a transient *status* enters the same retry path.
2. **Raise after exhaustion.** `Retrying(..., reraise=True)`: when the stop condition is met, the original
   exception (`TransientRequestError`, `TimeoutException`, or `ConnectError`) is re-raised. Stages are
   therefore required to `try`/`except TransientRequestError` to treat a permanently-failing request as a
   stage-level failure rather than a silent 503 response.
3. **Permanent statuses return immediately.** A 4xx response other than 429 (e.g. 404) is **not**
   retried — it is returned to the caller unchanged.
4. **`max_retries` = total attempts.** `stop_after_attempt(settings.max_retries)` means the default
   `max_retries=3` is **three attempts total** (one initial + two retries), **not** four. This is the
   Tenacity idiom and the literal reading of "budget = `WK_MAX_RETRIES`".
5. **Backoff curve.** `wait_exponential(multiplier=2, exp_base=2, max=30)` → ~2 s, 4 s, 8 s…, capped at
   30 s.
6. **Politeness on every attempt.** The politeness sleep `delay + U(0, jitter)` runs **before every
   attempt, including retries** (see ADR-0007 for the jitter primitive). This makes a retrying request
   slower but never hammering.
7. **Test seam.** `WhakoomSession(settings, *, client=None, retry_wait=None)` accepts an injectable
   `client` (tests pass an `httpx.MockTransport` client) and an injectable `retry_wait` (tests pass
   `wait_none()`). Politeness is neutralized in tests via `Settings(delay_seconds=0.0, jitter_seconds=0.0)`.

## Consequences

**Positive:** one centralized, fully tested retry policy; an explicit, documented error contract every
stage can rely on; deterministic and offline-testable (no real network, no real waiting); 404s and other
permanent errors flow straight through with no wasted attempts.

**Negative:** a stage that forgets to catch `TransientRequestError` will crash loudly on a persistently
transient URL — which is the intended "no silent failures" behavior (AGENTS §6), but it must be coded for.
Politeness-before-every-attempt makes a flapping URL costlier in wall-clock time. `max_retries=3` yielding
only two retries may surprise readers expecting three.

## Alternatives considered

- **Return the last 429/5xx response instead of raising.** Rejected: it hides the failure behind a normal
  `httpx.Response`, making "no silent failures" harder to enforce and forcing every call site to inspect
  status codes for retry outcomes it cannot act on.
- **`max_retries` = retries-after-first.** Rejected: ambiguous and fights Tenacity's `stop_after_attempt`
  primitive, which counts attempts. Documenting "total attempts" removes the ambiguity.
- **Honoring `Retry-After` on 429.** Deferred: a reasonable enhancement but out of scope for the initial
  layer; the exponential backoff already backs off.
- **Retry on result (return the response and use `retry_if_result`).** Rejected as more complex than the
  exception-driven path for the same outcome.
