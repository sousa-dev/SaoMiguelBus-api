# Architecture

djast follows consistent patterns designed for maintainability and AI-agent
compatibility.

## Core Principles

| Principle | Implementation |
|-----------|----------------|
| Service layer | Business logic in `services.py`, not views |
| Thin views | Views parse HTTP, call services, return responses |
| Type hints | PEP 484 annotations on all functions |
| Docstrings | Google-style on all public APIs |
| Feature toggles | Single `apps` list in `settings.py` |
| Explicit > implicit | Direct function calls over Django signals |

## Service Layer Pattern

```python
# stripe_payments/services.py
def create_checkout_session(*, user=None) -> CheckoutResult:
    """Create a Stripe Checkout Session."""
    ...

# stripe_payments/views.py
def payment(request):
    result = create_checkout_session(user=request.user)
    return redirect(result.checkout_url, code=303)
```

Services accept typed args (not `request` objects), return dataclasses, and
raise domain exceptions that views translate to HTTP responses.

## Current Service Modules

| Module | Responsibility |
|--------|----------------|
| `stripe_payments/services.py` | Payments, webhooks, coupons |
| `blog/services.py` | Post CRUD, filtering, search |
| `free_tools/services.py` | Tool queries, categories |

When adding features, create `services.py` in the relevant app.

## Agent Reference Docs

For full architecture details agents use internally:

| File | Content |
|------|---------|
| `.agentic/system_architecture.md` | Tech stack, URL map, deployment |
| `.agentic/coding_standards.md` | Patterns, testing, import order |

Human-facing guide to slash commands, rules, and `djast-*` agents:
[AI Agents, Rules & Commands](/docs/get_started/ai_agents).

## In This Section

| Page | Topic |
|------|-------|
| [URL Map](/docs/architecture/url_map) | Every route the project ships |
| [Directory Layout](/docs/architecture/directory_layout) | Annotated project tree |
