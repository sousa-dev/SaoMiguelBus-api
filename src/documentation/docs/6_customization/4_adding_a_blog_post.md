# Adding a Blog Post

Create and publish a blog post via Django admin.

## 1. Open Admin

Go to [http://127.0.0.1:8000/dashboard/admin/](http://127.0.0.1:8000/dashboard/admin/)
→ **Blog posts** → **Add blog post**.

## 2. Fill Required Fields

| Field | Guidance |
|-------|----------|
| Title | Clear, keyword-rich headline |
| Slug | URL-friendly (auto-generated from title) |
| Content | Markdown or HTML body |
| Category | Select or create a category |
| Author | Defaults to your admin user |
| Status | Set to **Published** when ready |

## 3. SEO Fields

| Field | Guidance |
|-------|----------|
| Meta title | 50–60 chars, include focus keyword |
| Meta description | 150–160 chars, compelling summary |
| Focus keyword | Primary SEO target |
| Canonical URL | Leave blank unless cross-posting |

## 4. CTA Configuration

Configure call-to-action fields for lead generation:

- CTA text (e.g. "Start your free trial")
- CTA URL (e.g. `/accounts/signup/`)

## 5. Multi-Language (Optional)

To create a translation:

1. Note the `translation_group` UUID of the original post.
2. Create a new post in the target language.
3. Set the same `translation_group` UUID on both posts.

## 6. Preview

Visit `/blog/<your-slug>/` and verify:

- [ ] Content renders correctly
- [ ] Meta tags in page source
- [ ] JSON-LD structured data present
- [ ] CTA displays
- [ ] Post appears on `/blog/` index

## 7. API Alternative

Create posts programmatically at `/blog/api/posts/`. See
`blog/AGENT_INSTRUCTIONS.md` for the full API reference.

## SEO Checklist

- [ ] Unique meta title and description
- [ ] Focus keyword in title, first paragraph, and at least one heading
- [ ] Internal links to relevant pages
- [ ] Featured image with alt text (if applicable)
- [ ] Post included in sitemap (automatic when published)
