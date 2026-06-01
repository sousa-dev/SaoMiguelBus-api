# Email

djast sends transactional email for account verification, payment receipts, and
custom notifications.

## Backends by Environment

| Environment | Backend | Config |
|-------------|---------|--------|
| Development (`DEBUG=True`) | Console | Emails print to terminal — no setup needed |
| Production (default) | Resend API | `RESEND_API_KEY` in `.env` |
| Production (SMTP) | SMTP | Set `USE_SMTP=True` + SMTP vars |

## Resend (Production Default)

```env
RESEND_API_KEY=re_xxxxxxxx
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

The custom backend lives at `shared/resend_backend.py`.

## SMTP (Alternative)

Set in `.env`:

```env
USE_SMTP=True
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-user
EMAIL_HOST_PASSWORD=your-password
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

## Verification Emails

Controlled by `ACCOUNT_EMAIL_VERIFICATION` in `.env`:

| Value | Behavior |
|-------|----------|
| `mandatory` | Must verify email before login |
| `optional` | Verification sent but not required |
| `none` | No verification emails |

## Sending Email from Code

Use Django's `send_mail` or the shared email utilities. In development, check
the terminal where `run.py` is running to see output.

Background email sending should use Celery tasks — see
[Background Tasks](/docs/background_tasks/).

## Troubleshooting

- **No emails in dev** — check the terminal, not your inbox.
- **Resend failures in prod** — verify `RESEND_API_KEY` and that
  `DEFAULT_FROM_EMAIL` uses a verified domain in Resend.
