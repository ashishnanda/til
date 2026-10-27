# til

My personal **Today I Learned** notes — short write-ups of things I pick up day to day.

Published with GitHub Pages at **https://ashishnanda.github.io/til/**.

## Add a new note

1. Create a file in `_posts/` named `YYYY-MM-DD-short-title.md`, e.g.
   `_posts/2026-10-28-bash-brace-expansion.md`.
2. Add front matter with a title and tags, then write the note in Markdown:

   ```markdown
   ---
   title: Bash brace expansion creates many files at once
   tags: [bash, cli]
   ---

   `touch file{1..3}.txt` creates `file1.txt`, `file2.txt` and `file3.txt`.
   ```

3. Commit and push to the default branch. GitHub Pages rebuilds the site
   automatically within a minute or two.

You can also do this entirely in the GitHub web UI: open `_posts/`, choose
**Add file → Create new file**, and commit.

## Issues as inbox

Open an issue in this repo (from the GitHub app on your phone, say) and a
workflow turns it into content. It only acts on issues **you** (the repo
owner) open, and only when the title starts with one of the commands below
(case doesn't matter). Any other issue is left alone.

When it works, the workflow commits the change, comments with a link, and
closes the issue. If something is wrong it comments with the reason and
leaves the issue open; nothing is committed. The site updates after GitHub
Pages rebuilds (a minute or two).

### Save a link — `save link: <url>`

```
Title: save link: https://jvns.ca/blog/2024/02/16/popular-git-config-options/
Body:  Recommended in the team chat; check the diff3 bit.
```

Adds the link to the **To read** list on [/reading/](https://ashishnanda.github.io/til/reading/),
with the page's title (or the URL if the title can't be fetched) and the body
as your note. Only `http://` / `https://` URLs are accepted; a URL that's
already saved is not added twice.

### Mark something read — `read: <#issue or search text>`

```
Title: read: #14
Body:  Turned on zdiff3 and rerere. Worth it.
```

```
Title: read: popular git config
```

`#14` picks the link saved by issue #14. Anything else matches part of the
title or URL (case-insensitive). With exactly one match, it moves to **Read**
with today's date, and the body (if any) replaces your note. With several
matches you get a list with their issue numbers (open a new issue with
`read: #<n>`); with none you get the three closest titles.

### Write a note — `TIL: <title>`

```
Title: TIL: git switch - jumps back to the previous branch
Body:
Like `cd -`, but for branches:

    git switch -

Tags: git, cli
```

Creates `_posts/YYYY-MM-DD-<slug>.md` dated today. The body becomes the note
(Markdown). A `Tags: a, b` line is turned into tags and removed from the text.

Notes from issues are sanitised: `{{ }}` / `{% %}` and HTML show up as plain
text instead of being run, so if you want real Liquid or HTML, edit the file
afterwards.

### Limits

- Title up to 200 characters, body up to 5000.
- Issues opened in very quick succession run one at a time. GitHub keeps only
  one *waiting* run, though, so if you open three at once the middle one can
  be cancelled and stay open untouched; open it again as a new issue.

## Enable GitHub Pages (one time)

Repository **Settings → Pages → Build and deployment**: set **Source** to
*Deploy from a branch*, pick the default branch and `/ (root)`, and save.

## Preview locally (optional)

Requires Ruby and Bundler.

```sh
bundle config set --local path vendor/bundle
bundle install
bundle exec jekyll serve
```

Then open http://localhost:4000/til/.

Inbox tests:

```sh
python3 -m pip install -r scripts/requirements-dev.txt
python3 -m pytest -q tests
```

See [CLAUDE.md](CLAUDE.md) for the site structure and conventions.
