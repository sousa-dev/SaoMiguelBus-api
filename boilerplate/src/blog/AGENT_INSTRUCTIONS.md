# Blog Agent Instructions

> How AI agents should create, update, and manage blog posts in djast.
> Read this file before creating any blog content.

---

## Creating a Blog Post

### Via the API (recommended for agents)

```bash
# Create a new post
curl -X POST http://localhost:8000/blog/api/posts/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token YOUR_TOKEN" \
  -d '{
    "title": "How to Reduce SaaS Churn: The Complete Guide",
    "slug": "how-to-reduce-saas-churn",
    "body": "<h2>Introduction</h2><p>...</p>",
    "excerpt": "Learn proven strategies to reduce churn and boost retention.",
    "meta_title": "Reduce SaaS Churn: Proven Strategies for 2025",
    "meta_description": "Discover 7 proven strategies to reduce SaaS churn and increase customer lifetime value. Actionable tips from industry experts.",
    "focus_keyword": "reduce SaaS churn",
    "language": "en",
    "status": "draft",
    "category_slug": "saas-growth",
    "tag_slugs": ["retention", "metrics", "saas"],
    "cta_text": "Download the Churn Reduction Playbook",
    "cta_url": "https://yourdomain.com/resources/churn-playbook",
    "lead_magnet_title": "The SaaS Churn Reduction Playbook",
    "featured_image_alt": "Dashboard showing churn reduction metrics"
  }'
```

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/blog/api/posts/` | List posts (filterable by `lang`, `category`, `tag`, `q`, `sort`) |
| POST | `/blog/api/posts/` | Create a post |
| GET | `/blog/api/posts/<slug>/` | Get post by slug |
| PUT | `/blog/api/posts/<slug>/` | Full update |
| PATCH | `/blog/api/posts/<slug>/` | Partial update |
| DELETE | `/blog/api/posts/<slug>/` | Delete a post |
| GET | `/blog/api/categories/` | List categories |
| POST | `/blog/api/categories/` | Create a category |
| GET | `/blog/api/tags/` | List tags |
| POST | `/blog/api/tags/` | Create a tag |

### Via Python Service Layer

```python
from blog.services import CreatePostInput, create_post

post = create_post(CreatePostInput(
    title="How to Reduce SaaS Churn",
    body="<h2>Introduction</h2><p>...</p>",
    language="en",
    meta_title="Reduce SaaS Churn: Proven Strategies",
    meta_description="Discover 7 proven strategies to reduce SaaS churn.",
    focus_keyword="reduce SaaS churn",
    category_slug="saas-growth",
    tag_slugs=["retention", "metrics"],
    status="published",
    cta_text="Get the Free Playbook",
    cta_url="https://yourdomain.com/playbook",
    lead_magnet_title="The Churn Playbook",
))
```

---

## GA4 Event Tracking

- `post_view` fires automatically on published post pages (`post_detail.html`)
- Set `cta_text` and `cta_url` — `cta_block.html` tags `blog_cta_click`
- Inline CTAs in body HTML: add `data-ga-event="blog_cta_click"` with `post_slug` in params
- Listing cards: pass `list_context` to `post_card.html` (`index`, `category`, `related`, etc.)

See `/docs/customization/event_tracking` for the full taxonomy.

---

## SEO Requirements for Every Post

Every post **must** have these fields filled for optimal SEO:

### Required
- `title` — Display title (max 250 chars). Include primary keyword.
- `body` — Full HTML content with proper heading hierarchy (H2, H3).
- `meta_title` — 50-70 characters. Primary keyword near the front.
- `meta_description` — 150-160 characters. Compelling, includes keyword.
- `slug` — URL-safe, keyword-rich, lowercase with hyphens.

### Strongly Recommended
- `focus_keyword` — The single keyword/phrase this post targets.
- `excerpt` — 1-2 sentence summary for index cards (max 500 chars).
- `featured_image` + `featured_image_alt` — Hero image with descriptive alt.
- `category` — One primary category per post.
- `tags` — 3-5 relevant tags.
- `cta_text` + `cta_url` — Lead generation CTA.

---

## Content Structure Template

Use this heading hierarchy for every post:

```html
<h2>Introduction / Hook</h2>
<p>Opening paragraph that hooks the reader. State the problem.</p>

<h2>Major Section 1 (secondary keyword)</h2>
<p>Content...</p>
<h3>Subsection 1a</h3>
<p>Content...</p>

<h2>Major Section 2 (secondary keyword)</h2>
<p>Content...</p>

<h2>Major Section 3 (long-tail keyword variation)</h2>
<p>Content...</p>

<h2>Key Takeaways</h2>
<ul>
  <li>Takeaway 1</li>
  <li>Takeaway 2</li>
  <li>Takeaway 3</li>
</ul>

<h2>Frequently Asked Questions</h2>
<h3>Question 1?</h3>
<p>Answer...</p>
<h3>Question 2?</h3>
<p>Answer...</p>
```

### Rules
- One H1 per page (the `title` field — rendered by the template).
- Use H2 for major sections, H3 for subsections. Never skip levels.
- Add a heading every 200-300 words.
- Keep headings under 70 characters.
- Use natural keyword variations across H2s.

---

## CTA Placement Strategy

The template automatically places the main CTA after the post body. For
inline CTAs within the content, insert this HTML:

```html
<div class="my-8 p-6 bg-blue-50 border border-blue-200 rounded-xl">
  <h3 class="text-lg font-bold text-blue-900 mb-2">Free Resource</h3>
  <p class="text-blue-700 mb-3">Description of the lead magnet...</p>
  <a href="YOUR_URL"
     class="inline-block bg-blue-600 text-white font-bold px-6 py-3 rounded-lg hover:bg-blue-700">
    Get the Free Guide →
  </a>
</div>
```

**Best positions for inline CTAs:**
1. After the first major section (~25% through the post)
2. At ~60% through the post
3. After the conclusion (handled automatically by the template)

---

## Multi-Language Posts

### Creating a Translation

```python
# Create the English version first
en_post = create_post(CreatePostInput(
    title="How to Reduce Churn",
    body="...",
    language="en",
    status="published",
))

# Create the French translation, linked to the English version
fr_post = create_post(CreatePostInput(
    title="Comment Réduire le Churn",
    slug="comment-reduire-le-churn",
    body="...",
    language="fr",
    status="published",
    translation_of_slug="how-to-reduce-churn",  # Links via translation_group
))
```

### Via API
Set `translation_of_slug` to the slug of any existing translation. The
system automatically assigns the same `translation_group` UUID.

### hreflang Tags
Generated automatically in the template from the `translation_group`.
No manual intervention needed.

---

## SEO Checklist Before Publishing

- [ ] `meta_title` is 50-70 characters and includes the focus keyword
- [ ] `meta_description` is 150-160 characters and is compelling
- [ ] `slug` is keyword-rich, lowercase, hyphen-separated
- [ ] `focus_keyword` is set
- [ ] Post body has proper H2/H3 heading hierarchy
- [ ] Featured image has descriptive `featured_image_alt` text
- [ ] At least one `category` is assigned
- [ ] 3-5 `tags` are assigned
- [ ] CTA is configured (`cta_text`, `cta_url`)
- [ ] Content is 1000+ words for SEO depth
- [ ] Internal links to other blog posts are included
- [ ] External links to authoritative sources are included

---

## Sitemap

The sitemap is automatically generated and cached (1 hour) at:
- `/sitemap.xml` — Index
- `/sitemap-blog-posts.xml` — All published posts
- `/sitemap-blog-categories.xml` — Category pages

Posts appear in the sitemap within 1 hour of publishing. No manual
regeneration is needed.
