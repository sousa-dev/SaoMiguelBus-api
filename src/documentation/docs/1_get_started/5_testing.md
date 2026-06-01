# Testing

djast targets **≥80% line coverage on service modules** (`*/services.py`).
Tests use **pytest** with **pytest-django**; Stripe and email are mocked — never hit real APIs.

## Install dev dependencies

From the repo root (after `python setup.py`):

```bash
source .venv/bin/activate
pip install -r src/requirements-dev.txt
```

## Run tests

```bash
cd src
pytest
```

`python manage.py test` also works — it shows a short notice and runs pytest (including any extra args, e.g. `python manage.py test blog/tests/`).

## Coverage gate (service modules)

From `src/`:

```bash
coverage run -m pytest
coverage report --fail-under=80
```

Optional HTML report:

```bash
coverage html
open htmlcov/index.html
```

Coverage is scoped to:

- `blog/services.py`
- `free_tools/services.py`
- `stripe_payments/services.py`

Configuration lives in `src/.coveragerc` (run commands from `src/`).

## Test layout

```
<app>/tests/
├── __init__.py
├── test_services.py   # priority — business logic
├── test_models.py
└── test_views.py
```

## Writing tests

- Use `@pytest.mark.django_db` for database tests.
- Mock external services: `stripe.*`, `send_mail`, Resend.
- Name functions `test_<behavior>`.
- Prefer service-layer tests over full HTTP when logic lives in `services.py`.

## AI agents

| Agent / rule | Use for |
|--------------|---------|
| `djast-qa-test-engineer` | New tests, mocks, coverage gaps |
| `.cursor/rules/tests.mdc` | Conventions and layout |
| `.agentic/coding_standards.md` §6 | Canonical testing standards |

## Next steps

- [First Run](/docs/get_started/first_run) — start the dev server
- [AI Agents](/docs/get_started/ai_agents) — delegate test work to `djast-qa-test-engineer`
