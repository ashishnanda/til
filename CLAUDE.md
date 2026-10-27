# CLAUDE.md

Personal "Today I Learned" notes site, built by **GitHub Pages' built-in Jekyll**
(no GitHub Actions, no custom plugins). Published at
`https://ashishnanda.github.io/til/`.

## Structure

```
_config.yml            Site settings. baseurl is "/til" (the repo name).
_posts/                One Markdown file per note: YYYY-MM-DD-title.md
_layouts/default.html  Page shell: <head>, header/nav, footer
_layouts/note.html     Single-note page (applied to all posts via `defaults`)
_includes/note-list.html  Date / title / tags list, used by home and tags pages
_includes/tags.html    Tag pills linking to /tags/#<tag>
index.html             Home page: all notes, newest first
tags.html              /tags/ — every tag with its notes
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
- No JavaScript is needed or used.

## Building / checking

```sh
bundle config set --local path vendor/bundle
bundle install
LANG=C.UTF-8 bundle exec jekyll build    # must finish with no errors
bundle exec jekyll serve                 # http://localhost:4000/til/
```

`_site/`, `vendor/`, `.bundle/` and `Gemfile.lock` are git-ignored.
