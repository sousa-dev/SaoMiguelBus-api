# Blog

SEO-optimized, multi-language lead-generation blog.

## URLs

| Path | Purpose |
|------|---------|
| `/blog/` | Index — filter by category, language, search, sort |
| `/blog/<slug>/` | Post detail with SEO meta, JSON-LD, hreflang, CTAs |
| `/blog/category/<slug>/` | Category archive |
| `/blog/tag/<slug>/` | Tag archive (noindexed) |
| `/blog/author/<username>/` | Author archive |
| `/blog/api/posts/` | REST API — list/create posts |
| `/blog/api/posts/<slug>/` | REST API — get/update/delete post |
| `/blog/api/categories/` | REST API — categories |
| `/blog/api/tags/` | REST API — tags |

## Admin Workflow

1. Go to `/dashboard/admin/` → **Blog posts**.
2. Create a post with title, slug, content, and category.
3. Fill SEO fields: `meta_title`, `meta_description`, `focus_keyword`.
4. Configure CTA fields for lead generation.
5. Set status to **Published**.

See [Adding a Blog Post](/docs/customization/adding_a_blog_post) for a
step-by-step walkthrough.

## SEO Features

- Per-post meta title, description, focus keyword, canonical URL
- JSON-LD structured data (`BlogPosting`, `BreadcrumbList`)
- Open Graph + Twitter Card meta tags
- `hreflang` tags for multi-language posts via `translation_group` UUID
- Included in `/sitemap.xml`

## Multi-Language

Posts link translations via a shared `translation_group` UUID. Create one post
per language and assign the same group ID.

## API Access

Full CRUD at `/blog/api/`. See `blog/AGENT_INSTRUCTIONS.md` for the complete
API reference (intended for agents; humans can use admin or API).

## Enable / Disable

```python
('blog', True),  # src/src/settings.py
```
