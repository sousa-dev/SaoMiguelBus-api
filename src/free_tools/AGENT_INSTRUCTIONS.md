# Free Tools Agent Instructions

> How AI agents should create and manage free tool pages in djast.
> Read this before building any new tool.

---

## Architecture

Each free tool consists of two parts:

1. **A `FreeTool` database record** — stores SEO metadata, CTA config,
   and a reference to the tool's template.
2. **A Django template** — implements the interactive tool UI (HTML + JS).
   Located in `free_tools/templates/free_tools/tools/`.

The `tool_detail.html` wrapper template handles the page chrome (header,
breadcrumbs, SEO meta, JSON-LD, CTA block, description). The per-tool
template is included via `{% include tool.template_name %}`.

---

## Adding a New Free Tool

### Step 1: Create the tool template

Create a new file in `free_tools/templates/free_tools/tools/`:

```
free_tools/templates/free_tools/tools/my_new_tool.html
```

This template is included inside a `<div>` wrapper — do NOT extend any
base template. Just write the tool's HTML and `<script>` tags.

Example structure:

```html
<div id="my-tool">
    <div class="mb-6">
        <!-- Input controls -->
    </div>
    <div class="relative">
        <!-- Output area -->
    </div>
    <div class="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-100">
        <!-- Usage instructions -->
    </div>
</div>

<script>
// Tool logic — keep it client-side when possible
</script>
```

### Step 2: Register via API (or admin)

```bash
# Create the category (if new)
curl -X POST http://localhost:8000/tools/api/categories/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token YOUR_TOKEN" \
  -d '{
    "name": "Generators",
    "slug": "generators",
    "description": "Free code and key generators for developers.",
    "icon_class": "fas fa-cogs"
  }'

# Create the tool
curl -X POST http://localhost:8000/tools/api/tools/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token YOUR_TOKEN" \
  -d '{
    "name": "My New Tool",
    "slug": "my-new-tool",
    "tagline": "One-line description of what this tool does.",
    "description": "<h2>What is this tool?</h2><p>Detailed SEO description...</p>",
    "template_name": "free_tools/tools/my_new_tool.html",
    "meta_title": "My New Tool - Free Online | djast",
    "meta_description": "Use this free tool to... 150-160 chars.",
    "focus_keyword": "my new tool",
    "icon_class": "fas fa-magic",
    "category_slug": "generators",
    "language": "en",
    "status": "published",
    "sort_order": 10,
    "cta_text": "Build faster with djast",
    "cta_url": "https://djast.dev",
    "lead_magnet_title": "djast — Django SaaS Boilerplate"
  }'
```

### Step 3: Verify

Visit `/tools/my-new-tool/` and check:
- Tool UI works correctly
- SEO meta tags are present (View Source → search for `og:title`)
- JSON-LD structured data is present
- Breadcrumbs display correctly
- CTA block renders below the tool
- Tool appears on `/tools/` index page

---

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/tools/api/tools/` | List published tools |
| POST | `/tools/api/tools/` | Create a tool |
| GET | `/tools/api/tools/<slug>/` | Get by slug |
| PUT | `/tools/api/tools/<slug>/` | Full update |
| PATCH | `/tools/api/tools/<slug>/` | Partial update |
| DELETE | `/tools/api/tools/<slug>/` | Delete |
| GET | `/tools/api/categories/` | List categories |
| POST | `/tools/api/categories/` | Create a category |

---

## SEO Requirements

Every tool **must** have:

- `meta_title` — 50-70 chars, includes the tool name + "Free Online"
- `meta_description` — 150-160 chars, action-oriented
- `focus_keyword` — the primary search term
- `tagline` — one-liner for the index card
- `description` — 300+ words HTML below the tool UI for SEO depth
- `icon_class` — Font Awesome class for the tool card

### Description SEO Template

```html
<h2>What is [Tool Name]?</h2>
<p>Explain what the tool does and why it's useful.</p>

<h2>How to Use</h2>
<p>Step-by-step instructions.</p>

<h2>Why You Need [Tool Purpose]</h2>
<p>Explain the problem this solves.</p>

<h2>Frequently Asked Questions</h2>
<h3>Is this tool free?</h3>
<p>Yes, completely free with no signup required.</p>
<h3>Is my data safe?</h3>
<p>All processing happens in your browser. No data is sent to our servers.</p>
```

---

## Tool Design Guidelines

1. **Client-side first** — Process data in the browser when possible. No
   server round-trips = instant results + no data privacy concerns.
2. **Copy to clipboard** — Every tool with output should have a copy button.
3. **Responsive** — Tools must work on mobile.
4. **Accessible** — Use proper labels, aria attributes, and focus states.
5. **Instant** — Generate results on page load or on first interaction.

---

## GA4 Event Tracking (required)

Every tool template must fire these events via `window.djast`:

| Event | When |
|-------|------|
| `tool_view` | Automatic on `tool_detail.html` — do not duplicate in partial |
| `tool_started` | `djast.trackOnce('tool_started_<slug>', ...)` on first interaction |
| `tool_generate` | Each generate/calculate action |
| `tool_copy_result` | Successful clipboard copy |

Reference implementation: `free_tools/templates/free_tools/tools/secret_key_generator.html`

Full taxonomy: `/docs/customization/event_tracking`

---

## Existing Tools

| Slug | Template | Category |
|------|----------|----------|
| `django-secret-key-generator` | `free_tools/tools/secret_key_generator.html` | Security |

---

## Multi-Language

Same pattern as the blog: set `translation_of_slug` when creating via API,
or manually assign the same `translation_group` UUID in the admin.
