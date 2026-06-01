# URL Map

All routes shipped by djast. Routes for disabled apps are not registered.

## Core

| Path | App | Purpose |
|------|-----|---------|
| `/` | `app` or `landing_page` | Dashboard or marketing page |
| `/app/` | `app` | Dashboard (when landing_page enabled) |
| `/product/` | `app` | Product detail page |
| `/media/<path>` | `app` | Media file serving |
| `/dashboard/admin/` | Django admin | Admin panel |
| `/robots.txt` | — | Robots exclusion |
| `/sitemap.xml` | sitemaps | XML sitemap index |

## Authentication

| Path | App | Purpose |
|------|-----|---------|
| `/login/` | `user_management` | Redirect to allauth login |
| `/logout/` | `user_management` | Redirect to allauth logout |
| `/accounts/*` | allauth | Login, signup, OAuth, verification |

## Documentation

| Path | App | Purpose |
|------|-----|---------|
| `/docs/` | `documentation` | Docs home |
| `/docs/<section>/` | `documentation` | Section index |
| `/docs/<section>/<page>/` | `documentation` | Doc page |
| `/docs/search/` | `documentation` | Full-text search |

## Payments

| Path | App | Purpose |
|------|-----|---------|
| `/payment/pay/` | `stripe_payments` | Initiate checkout |
| `/payment/successful/` | `stripe_payments` | Payment success |
| `/payment/cancelled/` | `stripe_payments` | Payment cancelled |
| `/payment/webhook/` | `stripe_payments` | Stripe webhook |

## Legal

| Path | App | Purpose |
|------|-----|---------|
| `/legal/privacy-policy/` | `legal` | Privacy policy |
| `/legal/terms-of-service/` | `legal` | Terms of service |
| `/legal/licenses/` | `legal` | Licenses |

## Blog

| Path | App | Purpose |
|------|-----|---------|
| `/blog/` | `blog` | Blog index |
| `/blog/<slug>/` | `blog` | Post detail |
| `/blog/category/<slug>/` | `blog` | Category archive |
| `/blog/tag/<slug>/` | `blog` | Tag archive |
| `/blog/author/<username>/` | `blog` | Author archive |
| `/blog/api/posts/` | `blog` | API: list/create |
| `/blog/api/posts/<slug>/` | `blog` | API: get/update/delete |
| `/blog/api/categories/` | `blog` | API: categories |
| `/blog/api/tags/` | `blog` | API: tags |

## Free Tools

| Path | App | Purpose |
|------|-----|---------|
| `/tools/` | `free_tools` | Tools index |
| `/tools/<slug>/` | `free_tools` | Tool page |
| `/tools/category/<slug>/` | `free_tools` | Category archive |
| `/tools/api/tools/` | `free_tools` | API: list/create |
| `/tools/api/tools/<slug>/` | `free_tools` | API: get/update/delete |
| `/tools/api/categories/` | `free_tools` | API: categories |

## Sitemaps

| Path | Purpose |
|------|---------|
| `/sitemap.xml` | Sitemap index |
| `/sitemap-<section>.xml` | Section sitemap |

## Updating This Map

When adding or removing URL patterns, update this page. See
[Maintaining Docs](/docs/maintaining_docs/).
