# ADR-0007 — Bandit-safe randomness and hashing

- **Status:** Accepted
- **Date:** 2026-08-02
- **Supersedes:** (none)
- **Related:** ADR-0006 (HTTP retry contract — consumes the jitter primitive defined here)

## Context

Phase 2 introduced two uses of standard-library primitives that Bandit flags by default:

1. **Politeness jitter.** `WhakoomSession._polite_sleep()` adds uniform jitter
   `U(0, WK_JITTER_SECONDS)` to the per-request delay. The obvious implementation is
   `random.uniform(0, jitter)`, which Bandit's **B311** ("Standard pseudo-random generators are not
   suitable for security/cryptographic purposes") flags.
2. **Raw-archive filename digest.** `http/archive.py` derives a collision-safe filename key from the
   source URL. The obvious choice is `hashlib.sha1(...)[:8]`, which Bandit's **B324** ("Use of weak MD4,
   MD5, or SHA1 hash for security") flags.

`AGENTS.md §2` forbids disabling rules or adding `# nosec` suppressions **without explicit user
permission**. Both uses here are non-security (rate-limiting jitter; a content-addressed filename), so the
flag is a false positive — but it must still be cleared without suppression.

## Decision

Use the Bandit-*safe* standard-library primitives in both cases, and treat this as a project-wide
precedent for any future non-security randomness or hashing:

1. **Jitter → `random.SystemRandom`.** The session holds `self._rng = random.SystemRandom()` and calls
   `self._rng.uniform(0, jitter)`. `SystemRandom` is the cryptographically-secure generator and is **not**
   in Bandit's B311 blacklist; additionally, calling `.uniform` on the instance (`self._rng.uniform(...)`)
   is not matched as the `random.uniform` pattern.
2. **Filename digest → `hashlib.sha256`.** `_url_to_key` uses
   `hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]`. SHA-256 is not in Bandit's weak-hash blacklist
   (B324). The key shape is `sanitized_path[:120]_sha256[:8]`, so collision safety comes from the hash and
   readability from the path slug.

**Project precedent:** when a Bandit-flagged primitive is genuinely inappropriate for a non-security use
and `# nosec` cannot be used without permission, prefer the secure equivalent (`random.SystemRandom`,
`hashlib.sha256`/`sha512`, `secrets`) rather than suppressing the finding.

## Consequences

**Positive:** zero Bandit findings with no `# nosec` suppressions, keeping AGENTS compliance; one clear
convention to reuse; the filename digest remains deterministic (important — re-fetches overwrite the same
archive file rather than duplicating it).

**Negative:** `SystemRandom` is marginally slower than `random.uniform`, which is irrelevant at our request
rate (~1 req/1.5 s). SHA-256 is marginally more CPU than SHA-1, which is irrelevant for short URL strings.

## Alternatives considered

- **`# nosec B311` / `# nosec B324` inline suppressions with a justification comment.** Rejected: AGENTS §2
  requires explicit user permission for suppression, and the secure equivalent avoids the question
  entirely.
- **`secrets` module for jitter.** Rejected: `secrets` has no direct `uniform`; deriving a float from
  `secrets.randbelow` is more code for no benefit over `SystemRandom.uniform`.
- **Deterministic (non-random) jitter.** Rejected: defeats the purpose of jitter (de-phasing the request
  cadence to avoid a predictable footprint).
