# Database Hygiene Notes

Roundup currently keeps raw articles and generated clusters indefinitely. That is safest for user data, but long-running installs will eventually need an explicit retention policy.

TODO:
- Decide whether stale unclustered articles should be archived, hidden, or deleted after a configurable age.
- Decide whether hidden clusters with no promoted history should be compacted or archived after a configurable age.
- Add a non-destructive maintenance command that reports candidate cleanup counts before changing anything.
- Consider a safe canonical URL duplicate remediation workflow before adding a unique constraint on `articles.canonical_url`.
