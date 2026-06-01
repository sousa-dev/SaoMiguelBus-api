# Event Tracking

How to instrument new pages, CTAs, and tools with GA4 in djast.

## Quick Checklist

1. Extend a base that includes `{% include "shared/plugins/google-analytics.html" %}`.
2. Set `GOOGLE_ANALYTICS_ID` in `.env` (see [Analytics](/docs/configuration/analytics)).
3. Tag static interactions with `data-ga-event` + `data-ga-params`.
4. Call `window.djast.track()` for dynamic JS (tool runners, tabs, video).
5. Opt out of auto-capture with `data-ga-skip` on an element or ancestor.

## Helper API

Loaded globally as `window.djast` from `static/js/djast-analytics.js`:

```javascript
// Fire a custom event (merges GA_PAGE defaults)
djast.track('feature_tab_view', { feature: 'agents', page_section: 'features' });

// Fire once per browser session (sessionStorage)
djast.trackOnce('purchase_cs_xxx', 'purchase', { transaction_id: 'cs_xxx', value: 159 });

// Set user id after login (also set server-side via gtag config when authenticated)
djast.identify('42');

// Manual pageview (rare — gtag config already sends pageviews)
djast.pageview({ page_section: 'checkout' });
```

## Declarative Tagging

```html
<a href="/blog/"
   data-ga-event="nav_cta_click"
   data-ga-params='{"cta_label":"blog","page_section":"nav"}'>
  Blog
</a>

<form method="post" action="/payment/pay/"
      data-ga-event="begin_checkout"
      data-ga-params='{"plan":"premium","value":159,"currency":"USD"}'>
  ...
</form>
```

| Attribute | Purpose |
|-----------|---------|
| `data-ga-event` | Event name (snake_case) |
| `data-ga-params` | JSON object of extra parameters |
| `data-ga-once` | Fire only once per page load (click) |
| `data-ga-skip` | Skip all auto-instrumentation under this subtree |
| `data-ga-skip-auto` | Skip auto `form_submit` on this form |
| `data-ga-skip-outbound` | Skip auto `outbound_click` on this link |

## Auto-Instrumentation

When `GOOGLE_ANALYTICS_ID` is set, these fire without manual tags:

| Event | Trigger |
|-------|---------|
| `outbound_click` | External `<a href>` |
| `contact_click` | `mailto:` / `tel:` links |
| `file_download` | Links to `.pdf`, `.zip`, `.json`, images, etc. |
| `form_submit` | Any form submit (unless `data-ga-skip-auto`) |
| `video_play` / `video_complete` | YouTube embeds with IFrame API |
| `scroll_depth` | 25/50/75/90/100% on pages with `data-ga-scroll="true"` |
| `js_error` | Uncaught JS errors |
| `promise_rejection` | Unhandled promise rejections |

Enable scroll tracking on a page:

```html
<body data-ga-scroll="true">
```

## Event Taxonomy (canonical names)

Python constants: `shared/analytics.py` (`EVENT_NAMES`, `PAGE_TYPES`).

### Landing & app

| Event | When |
|-------|------|
| `begin_checkout` | Payment form submit |
| `feature_tab_view` | LP features tab change |
| `nav_cta_click` | Nav/footer section CTAs |

### Blog

| Event | When |
|-------|------|
| `post_view` | Post detail load |
| `post_card_click` | Card/title/read-more click |
| `blog_cta_click` | CTA block click |
| `search` | Blog index filter submit |
| `pagination_click` | Page navigation |
| `translation_switch` | Language link on post |

### Free tools

| Event | When |
|-------|------|
| `tool_view` | Tool detail load |
| `tool_started` | First interaction (once per session) |
| `tool_generate` | Generate / calculate action |
| `tool_copy_result` | Successful copy |
| `tool_cta_click` | Tool CTA block |

### Auth & payment

| Event | When |
|-------|------|
| `login` | `?login=success` query after redirect |
| `sign_up` | `?signup=success` query |
| `purchase` | Success page (`trackOnce` by `session_id`) |
| `checkout_cancelled` | Cancel page load |

## Tool Runner Template Pattern

Every new tool partial under `free_tools/templates/free_tools/tools/` should include:

```javascript
document.addEventListener('DOMContentLoaded', function () {
    djast.trackOnce('tool_started_MY-SLUG', 'tool_started', { tool_slug: 'MY-SLUG' });
});
// On generate: djast.track('tool_generate', { tool_slug: 'MY-SLUG', ... });
// On copy:    djast.track('tool_copy_result', { tool_slug: 'MY-SLUG' });
```

See `secret_key_generator.html` for the reference implementation.

## Blog CTA Pattern

`blog/components/cta_block.html` already tags `blog_cta_click`. For inline CTAs in
post HTML, add `data-ga-event` manually or use the CTA block via the API.

## Scaffolding

Slash commands and agents include a **Tracking** section — run `/new-free-tool`
or `/new-blog-post` and the agent will wire events by default.
