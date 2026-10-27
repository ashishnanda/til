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

See [CLAUDE.md](CLAUDE.md) for the site structure and conventions.
