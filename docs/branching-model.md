# Branching Model

Roundup keeps `main` as the only long-lived branch in this checkout.

Use short-lived branches for actual work:

- `feature/minor/<name>` for small product changes that merge back to `main`
- `feature/major/<name>` for larger multi-step work that still lands on `main`
- `support/<major.minor>` for a stabilized release line when a maintained release needs patching
- `bugfix/<version-or-ticket>` for fixes that must land on a support line first

Flow:

1. Branch work from `main` for new feature development.
2. Branch a support line only when a released version needs ongoing fixes.
3. Land bug fixes on the support line first.
4. Promote the support-line fix back to `main` by merge or cherry-pick, depending on release timing.

Rules:

- Keep `main` releasable.
- Keep feature branches short-lived.
- Do not leave stale topic branches around after merge.
- Prefer a new branch over piling unrelated work into an existing one.

This matches the release/support/bugfix pattern in the diagram: new feature work moves forward on `main`, while maintenance stays on a support line until it is released back.
