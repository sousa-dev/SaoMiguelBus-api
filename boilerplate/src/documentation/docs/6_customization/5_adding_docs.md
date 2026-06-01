# Adding Documentation

Add new pages to this `/docs` site.

## File Structure

```
src/documentation/docs/
├── N_section_name/          # numbered section directory
│   ├── index.md             # section landing page
│   ├── 1_page_name.md       # first page in sidebar
│   └── 2_another_page.md    # second page
```

## Naming Rules

| Element | Pattern | URL result |
|---------|---------|------------|
| Section dir | `N_slug/` e.g. `10_my_section/` | `/docs/my_section/` |
| Page file | `N_slug.md` e.g. `1_overview.md` | `/docs/my_section/overview` |
| Index | `index.md` | `/docs/my_section/` |

- `N` is a number controlling sort order in the sidebar.
- The engine strips numeric prefixes for URLs and display names.

## Step-by-Step

### Add a page to an existing section

1. Create `src/documentation/docs/2_configuration/6_new_topic.md`
2. Add a link from the section `index.md`
3. Restart is not needed — refresh `/docs/` in the browser

### Add a new section

1. Create directory: `src/documentation/docs/10_my_section/`
2. Add `index.md` as the landing page
3. Add numbered pages: `1_first_page.md`, etc.
4. The sidebar auto-discovers the new section on next page load

## Markdown Features

Supported extras:

- Fenced code blocks (```python, ```bash, etc.)
- Tables
- Raw HTML (for platform tabs — see [Install](/docs/get_started/install))

## Internal Links

Use absolute doc paths:

```markdown
See [Feature Toggles](/docs/configuration/feature_toggles).
```

## Preview Locally

```bash
cd src
python run.py
```

Visit [http://127.0.0.1:8000/docs/](http://127.0.0.1:8000/docs/).

## Search

New pages are automatically indexed by the search at `/docs/search/?q=...`.

## When Agents Must Update Docs

See [Maintaining Docs](/docs/maintaining_docs/) for the full mapping of code
changes to documentation pages.
