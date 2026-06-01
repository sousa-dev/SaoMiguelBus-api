# Troubleshooting

Common issues and fixes when working with djast.

## Tailwind CSS Not Building

**Symptoms:** Pages load without styles, unstyled HTML.

**Fixes:**

1. Use `python run.py` instead of `manage.py runserver` — run.py starts Tailwind.
2. Manually build:
   ```bash
   cd src
   python manage.py tailwind build
   ```
3. Check Node.js is installed (18+).
4. Install Tailwind deps:
   ```bash
   cd src
   python manage.py tailwind install
   ```

## Celery Tasks Not Executing

**Symptoms:** `.delay()` calls succeed but nothing happens.

**Fixes:**

1. Verify Redis is running: `redis-cli ping` → `PONG`
2. Start the worker:
   ```bash
   cd src
   celery -A src worker --loglevel=info
   ```
3. Check `CELERY_BROKER_URL` in `.env` matches your Redis instance.
4. Ensure the task module is importable (tasks in `app/tasks.py` are auto-discovered).
5. Check worker terminal for error tracebacks.

## Celery Beat Not Scheduling

**Symptoms:** Periodic tasks never fire.

**Fixes:**

1. Start beat separately:
   ```bash
   cd src
   celery -A src beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
   ```
2. Verify periodic tasks are **Enabled** in admin → Periodic Tasks.
3. Both worker AND beat must be running.

## Stripe Webhook Signature Failures

**Symptoms:** `400` on `/payment/webhook/`, "Invalid signature" in logs.

**Fixes:**

1. Verify `TEST_STRIPE_WEBHOOK_SECRET` (dev) or `STRIPE_WEBHOOK_SECRET` (prod) matches Stripe dashboard.
2. For local dev, use Stripe CLI:
   ```bash
   stripe listen --forward-to localhost:8000/payment/webhook/
   ```
   Copy the signing secret it prints to `.env`.
3. Ensure you're using test keys with test webhook secret (and live with live).

## Stripe Checkout: Empty `line_items[0][price]`

**Symptoms:** `500` or `503` on `/payment/pay/`, Stripe error:
`You passed an empty string for 'line_items[0][price]'`.

**Cause:** When `DEBUG=False`, djast reads **unprefixed** Stripe variables
(`PRODUCT_PRICE_ID`, not `TEST_PRODUCT_PRICE_ID`). Staging hosts often have only
`TEST_*` keys configured from local development.

**Fixes:**

1. Set unprefixed vars in staging/production env (values may still be Stripe
   **test-mode** keys — the prefix is djast naming, not Stripe mode):

   ```env
   DEBUG=False
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLIC_KEY=pk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   PRODUCT_PRICE_ID=price_...
   REDIRECT_DOMAIN=https://staging.djast.dev/payment
   ```

2. If you already have `TEST_PRODUCT_PRICE_ID`, copy its value to
   `PRODUCT_PRICE_ID`.
3. Run deploy checks before shipping:

   ```bash
   cd src
   python manage.py check --deploy
   ```

   Missing Stripe settings surface as `stripe_payments.E001` errors when
   `DEBUG=False`.

## OAuth Callback Mismatch

**Symptoms:** "Redirect URI mismatch" after Google/GitHub login.

**Fixes:**

1. Google Console → Authorized redirect URIs must include:
   ```
   http://127.0.0.1:8000/accounts/google/login/callback/
   ```
2. GitHub → OAuth App → Authorization callback URL:
   ```
   http://127.0.0.1:8000/accounts/github/login/callback/
   ```
3. For production, replace `127.0.0.1:8000` with your domain.
4. Verify `GOOGLE_CLIENT_ID` / `GITHUB_CLIENT_ID` match the OAuth app.

## SECRET_KEY Warning

**Symptoms:** `UserWarning: Please set a secure SECRET_KEY`.

**Fix:**

Generate a key at [/tools/django-secret-key-generator/](/tools/django-secret-key-generator/)
and set in `.env`:

```env
SECRET_KEY=your-generated-key
```

## Database Errors After Pull

**Symptoms:** `OperationalError` or missing column errors.

**Fix:**

```bash
cd src
python manage.py migrate
```

If migrations are corrupted in dev:

```bash
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

## Import Errors After Toggle Change

**Symptoms:** `ModuleNotFoundError` after disabling an app.

**Fix:**

1. Restart the dev server after changing the `apps` list.
2. Ensure no other code imports the disabled app directly.

## Docs Page 404

**Symptoms:** New doc page returns 404.

**Fixes:**

1. Check file naming: `N_slug.md` inside `N_section/` directory.
2. Verify numeric prefix is present (e.g. `1_install.md`, not `install.md`).
3. Ensure `('documentation', True)` in the `apps` list.

See [Adding Docs](/docs/customization/adding_docs).

## Still Stuck?

- Check `.agentic/system_architecture.md` for architecture details
- See [AI Agents](/docs/get_started/ai_agents) for Cursor commands, rules, and `djast-*` agents
- Search docs: `/docs/search/?q=your+query`
- Open an issue on GitHub
