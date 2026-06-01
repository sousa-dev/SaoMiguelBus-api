# Analytics (GA4)

djast ships Google Analytics 4 with custom events, auto-instrumentation, and
optional Google Consent Mode v2 for EEA traffic.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_ANALYTICS_ID` | *(empty)* | GA4 Measurement ID (`G-XXXXXXXXXX`). When empty, no scripts load. |
| `CONSENT_REQUIRED` | `False` | When `True`: Consent Mode default-denied + Accept/Reject banner |
| `GA_DEBUG_MODE` | `DEBUG` | Routes events to GA4 DebugView |

Add to `src/src/.env`:

```bash
GOOGLE_ANALYTICS_ID=G-XXXXXXXXXX
CONSENT_REQUIRED=False
GA_DEBUG_MODE=True
```

## Setup in Google Analytics

1. Create a GA4 property and web data stream.
2. Copy the **Measurement ID** (`G-...`) into `GOOGLE_ANALYTICS_ID`.
3. For local testing, open the site with `?ga_debug=1` or set `GA_DEBUG_MODE=True`.
4. Verify events in **Admin → DebugView**.

## Consent Mode (EEA)

Set `CONSENT_REQUIRED=True` before production traffic from the EEA. This:

- Boots gtag with all storage signals **denied** until the user chooses
- Shows a first-party Accept / Reject banner
- Persists choice in `localStorage` (`djast_consent_v1`)
- Calls `gtag('consent', 'update', ...)` on choice

Update your [Privacy Policy](/legal/privacy-policy/) to mention analytics cookies.

## Where Analytics Loads

The snippet lives in `shared/templates/shared/plugins/google-analytics.html` and
is included from every user-facing base template (landing, app, docs, legal,
Stripe, allauth).

## Custom Dimensions (recommended in GA4 UI)

Register these event parameters as custom dimensions for reporting:

| Parameter | Example values |
|-----------|----------------|
| `page_type` | `landing`, `blog_post`, `tool`, `payment` |
| `page_section` | `hero`, `pricing`, `tool_runner` |
| `post_slug` | `my-blog-post` |
| `tool_slug` | `django-secret-key-generator` |
| `plan` | `starter`, `premium`, `hero` |

## Funnel Events

| Step | Event |
|------|-------|
| CTA click | `begin_checkout` |
| Payment success page | `purchase` (deduped by `session_id`) |
| Payment cancelled | `checkout_cancelled` |
| Retry | `retry_payment` |

## See Also

- [Event Tracking Guide](/docs/customization/event_tracking) — helper API, `data-ga-*` attributes, taxonomy
- [Environment](/docs/get_started/environment) — all env vars
- [Production Environment](/docs/deployment/production_env) — production checklist
