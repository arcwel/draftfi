# Contributing to DraftFi

Thanks for your interest in improving DraftFi! This is a local-first,
privacy-preserving project — contributions that keep it that way are especially
welcome.

## Ground rules

- **Keep it local.** No feature may require sending user financial data off the
  machine. The LLM layer must remain a configurable local endpoint.
- **No premium locks.** Every feature stays free and open (MIT).
- Be respectful. See our short [Code of Conduct](#code-of-conduct) below.

## Development setup

See the [README](README.md) quick-start for backend + frontend setup.

## Before you open a PR

Backend:

```bash
cd backend && source .venv/bin/activate
ruff check .
pytest
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

CI (`.github/workflows/ci.yml`) runs all of the above on every PR.

## Commit style

- Small, focused commits with imperative messages ("Add CSV encoding fallback").
- New behavior should come with a test. The backend suite lives in
  `backend/tests/`.
- Database changes go through an **append-only** migration in
  `backend/app/db/schema.py` (never edit a shipped migration).

## Project conventions

- Backend: layered as `api → services → db/repository`. Routers stay thin;
  business logic lives in `services/`; SQL lives in `db/repository.py`.
- Frontend: state and side effects live in the Zustand store
  (`src/store/useStore.js`); components stay presentational where possible.

## Code of Conduct

Be kind and constructive. Harassment, discrimination, or hostile behavior of any
kind is not tolerated. Report concerns by opening a confidential issue or
contacting a maintainer. Maintainers may remove comments, commits, and
contributors that violate these principles.
