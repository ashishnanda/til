# CLAUDE.md

Personal "Today I Learned" notes site, built by **GitHub Pages' built-in Jekyll**
(no custom plugins; the site build itself uses no GitHub Actions). Published at
`https://ashishnanda.github.io/til/`. One Actions workflow, the **issue inbox**,
only *writes content* (see below); Pages still builds the site.

## Structure

```
_config.yml            Site settings. baseurl is "/til" (the repo name).
_posts/                One Markdown file per note: YYYY-MM-DD-title.md
_layouts/default.html  Page shell: <head>, header/nav, footer
_layouts/note.html     Single-note page (applied to all posts via `defaults`)
_includes/note-list.html  Date / title / tags list, used by home and tags pages
_includes/tags.html    Tag pills linking to /tags/#<tag>
_includes/reading-list.html  Reading-list entries (used by reading.html)
_data/reading.yml      Reading list data (written by the issue inbox)
index.html             Home page: all notes, newest first
tags.html              /tags/ — every tag with its notes
reading.html           /reading/ — "To read" and "Read" sections
.github/workflows/issue-inbox.yml  Issue inbox workflow (issues: opened)
scripts/inbox.py       Issue inbox logic (all parsing/validation/escaping)
scripts/requirements*.txt  Pinned Python deps (runtime / + pytest)
tests/test_inbox.py    pytest suite for scripts/inbox.py
404.html               Not-found page
assets/css/til.css     All styling (plain CSS, light + dark via prefers-color-scheme)
Gemfile                Local preview only (github-pages gem); GitHub ignores it
```

## Note format

File: `_posts/YYYY-MM-DD-short-kebab-title.md`. The date in the filename is the
note's date; the rest becomes the URL slug (`/til/YYYY/MM/DD/short-kebab-title/`).

```markdown
---
title: Human-readable title
tags: [git, cli]
---

Body in GitHub-flavoured Markdown. Fenced code blocks with a language
(```sh, ```css, ...) get syntax highlighting.
```

- `title` and `tags` are the only front matter needed. `layout: note` is set
  automatically by `defaults` in `_config.yml`.
- Tags: lowercase, short, single words or kebab-case (`git`, `css`, `github-pages`).
  Reuse existing tags where possible (see `/tags/`).
- Keep notes short and focused on one thing learned.

## Conventions

- **GitHub Pages compatibility is a hard constraint.** Only use plugins on the
  [GitHub Pages allow-list](https://pages.github.com/versions/) and list them in
  `_config.yml` `plugins:`. Currently: `jekyll-feed`, `jekyll-seo-tag`, `jekyll-sitemap`.
  GitHub Pages runs **Jekyll 3.x** — avoid Jekyll 4-only features (e.g. `include`
  params must be plain variables: `{% assign x = tag[1] %}` then `notes=x`).
- **Always use `relative_url`** for internal links/assets
  (`{{ '/tags/' | relative_url }}`, `{{ post.url | relative_url }}`) so the
  `/til` baseurl is applied.
- `theme: null` is deliberate: the site ships its own layouts and CSS. Don't add a
  theme, and don't name the stylesheet `assets/css/style.*` (collides with the
  default Pages theme).
- Styling: plain CSS only, in `assets/css/til.css`. All colors are CSS variables on
  `:root` with a `prefers-color-scheme: dark` override — add new colors to both.
  Keep it mobile-friendly (the list stacks below 34rem).
- No JavaScript is needed or used. `default.html` sends a Content-Security-Policy
  with `script-src 'none'` as a backstop; keep it (it would block any JS you add).
- **Escape titles on output** (`{{ page.title | escape }}`, `{{ note.title | escape }}`):
  titles may come from issues. Every value from `site.data.reading` must be
  output with `| escape` too.
- `scripts/`, `tests/` and `__pycache__` are in `_config.yml` `exclude`.

## Issue inbox

Issues the repo owner opens are turned into content by
`.github/workflows/issue-inbox.yml` → `scripts/inbox.py`. The command is the
issue title prefix (case-insensitive); anything else is left alone as a
normal issue.

| Title | Effect |
|---|---|
| `save link: <url>` | Append `{title, url, note, added, status: to-read, issue}` to `_data/reading.yml` (title fetched from the page, URL as fallback; duplicate URLs refused) |
| `read: #12` / `read: <text>` | Mark the entry saved by issue #12, or the single entry whose title/URL contains the text, as `status: read` with `read` timestamp; a non-empty body replaces `note`. Several or no matches → comment, nothing changed |
| `TIL: <title>` | Create `_posts/YYYY-MM-DD-<slug>.md`; body is the content, a `Tags: a, b` line becomes front-matter tags |

On success the script commits, pushes to the default branch, comments with
a link and closes the issue. On any error it comments and leaves the issue
open, with nothing committed. `added`/`read` are ISO timestamp strings
(`2026-10-27T12:30:00Z`) so the reading page can sort by them.

### Security rules — do not weaken

- Trigger is **only** `issues: types: [opened]`. The job runs only when
  `github.event.issue.user.login == github.repository_owner`, and
  `inbox.py` re-checks the author. Other authors get no comment and no commit.
- **Never put `${{ github.event.* }}` (or any user-controlled value) inside a
  `run:` script.** Pass it through `env:` and parse it in Python. Subprocesses
  in `inbox.py` use argument lists (no shell); text goes in via stdin.
- Permissions are exactly `contents: write` and `issues: write`; only the
  default `GITHUB_TOKEN`; every action is pinned to a full commit SHA
  (with the tag in a comment). Python deps are version-pinned.
- Job-level `concurrency: issue-inbox` (no cancel-in-progress) serialises runs.
- Filenames come only from `slugify()` (`[a-z0-9-]`, ≤ 60 chars). `atomic_write()`
  refuses any path other than `_data/reading.yml` or a file directly in `_posts/`.
- YAML is written only with `yaml.safe_dump` (never string formatting) and
  read with `yaml.safe_load`. Files are written atomically after all
  validation, so a failure never leaves partial changes.
- Post bodies go through `sanitize_markdown()`: every `{{`/`{%` is made literal
  (`{{ "{" }}`), `<` outside code becomes `&lt;`, kramdown `{:` is disabled, and
  non-http(s)/mailto link targets become `#`. Titles are stored verbatim
  in YAML and **escaped by the templates**; reading-list values likewise.
- Length limits: title ≤ 200, body ≤ 5000 chars; URLs must be `http(s)`.
  Page-title fetch: 10 s budget, ≤ 1 MB read, http(s) redirects only, never fatal.
- Run `python3 -m pytest -q tests` after any change to `inbox.py`, and add a
  test for any new input handling.

## Building / checking

```sh
bundle config set --local path vendor/bundle
bundle install
LANG=C.UTF-8 bundle exec jekyll build    # must finish with no errors
bundle exec jekyll serve                 # http://localhost:4000/til/

python3 -m pip install -r scripts/requirements-dev.txt
python3 -m pytest -q tests               # issue inbox tests; must all pass
```

`_site/`, `vendor/`, `.bundle/` and `Gemfile.lock` are git-ignored.
