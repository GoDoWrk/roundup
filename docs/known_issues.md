# Known Issues

This file tracks non-blocking issues found during product hardening checks.

## Current

- `pytest -q` may print a Windows temp cleanup `PermissionError` after reporting all tests passed. The test process exits successfully; this appears to be pytest cleanup of `pytest-current` under the local temp directory.
- Backend tests currently emit FastAPI `on_event` deprecation warnings from `app/main.py`. This does not affect runtime behavior, but the app should eventually move startup checks to a lifespan handler.
- Frontend tests emit React Router v7 future flag warnings. The current React Router v6 routes still work; the warnings should be addressed during a dependency upgrade pass.
- `docker compose build` currently reports 5 moderate npm audit findings during the frontend image install step. The build succeeds; dependency remediation should be handled as a separate dependency/security pass because forced audit fixes may introduce breaking upgrades.

## Verification Notes

- Fresh install should be checked with `docker compose build`, an isolated migration project, and the `/health`, `/api/clusters`, `/api/search`, `/debug/articles`, and `/debug/clusters` endpoints listed in `README.md`.
- If Docker is unavailable or local ports are occupied, record the exact skipped command and blocker in the PR note.
