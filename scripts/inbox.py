#!/usr/bin/env python3
"""Issues-as-inbox processor for the TIL site.

Run by .github/workflows/issue-inbox.yml on `issues: opened`. Every
user-controlled value (issue title, body, author) arrives through environment
variables and is parsed here -- never in shell. See CLAUDE.md ("Issue inbox")
for the security rules this file must keep.

Commands (issue title prefix, case-insensitive):
  save link: <url>   add a URL to _data/reading.yml
  read: <#n | text>  mark a reading-list entry as read
  TIL: <title>       create a note in _posts/
Anything else is ignored so normal issues keep working.
"""

import datetime as dt
import difflib
import html
import html.parser
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import yaml

MAX_TITLE = 200
MAX_BODY = 5000
MAX_SLUG = 60
MAX_TAGS = 10
MAX_TAG_LEN = 30
FETCH_TIMEOUT = 10  # seconds, for the whole page-title fetch
FETCH_MAX_BYTES = 1_000_000

READING_FILE = "_data/reading.yml"
POSTS_DIR = "_posts"
READING_HEADER = "# Reading list. Written by scripts/inbox.py (issue inbox); safe to edit by hand.\n"

COMMANDS = (
    ("save", re.compile(r"^\s*save\s+link\s*:\s*(.*)$", re.I | re.S)),
    ("read", re.compile(r"^\s*read\s*:\s*(.*)$", re.I | re.S)),
    ("til", re.compile(r"^\s*til\s*:\s*(.*)$", re.I | re.S)),
)


class InboxError(Exception):
    """A problem to report back on the issue (the issue stays open)."""


@dataclass
class Result:
    status: str  # "ignored" | "done" | "error"
    message: str = ""  # Markdown comment for the issue
    commit_message: str = ""
    paths: list = field(default_factory=list)  # repo-relative files written


@dataclass
class Issue:
    number: int
    title: str
    body: str
    author: str


# ---------------------------------------------------------------- text helpers

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f  ]")


def clean_line(text):
    """Single line of plain text: no control chars, collapsed whitespace."""
    text = _CONTROL.sub("", text or "")
    return re.sub(r"\s+", " ", text).strip()


def clean_body(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL.sub("", text).strip()


def code(text):
    """Inline code span for GitHub comments (no mentions, no formatting)."""
    text = clean_line(text) or " "
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    return f"{fence} {text} {fence}"


def slugify(text, fallback):
    """Lowercase letters, digits and single hyphens only; at most 60 chars."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > MAX_SLUG:
        slug = slug[:MAX_SLUG]
        if "-" in slug:
            slug = slug.rsplit("-", 1)[0]
        slug = slug.strip("-")
    return slug or fallback


# ------------------------------------------------- Liquid / Markdown escaping

def escape_liquid(text):
    """Make every `{{` and `{%` literal by emitting the brace from Liquid.

    `{{ "{" }}` renders a single `{`. Only braces followed by `{` or `%` are
    replaced, so the generated tag is never directly followed by `}`.
    """
    return re.sub(r"\{(?=[{%])", '{{ "{" }}', text)


_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(?<![\\`])(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_LINK_DEST = re.compile(r"(\]\(\s*<?)([^)\s>]*)")
_REF_DEF = re.compile(r"^(\s{0,3}\[[^\]]+\]:\s*<?)(\S*)")
_SAFE_SCHEMES = {"http", "https", "mailto"}


def _safe_dest(dest):
    probe = re.sub(r"[\s\x00-\x1f]", "", html.unescape(dest)).lower()
    scheme = re.match(r"^([a-z][a-z0-9+.-]*):", probe)
    if scheme and scheme.group(1) not in _SAFE_SCHEMES:
        return "#"
    return dest


def _escape_text(text):
    text = text.replace("<", "&lt;")  # no raw HTML or autolinks
    text = text.replace("{:", "&#123;:")  # no kramdown IAL/extensions
    text = _LINK_DEST.sub(lambda m: m.group(1) + _safe_dest(m.group(2)), text)
    text = _REF_DEF.sub(lambda m: m.group(1) + _safe_dest(m.group(2)), text)
    return text


def _escape_inline(line):
    out, pos = [], 0
    for m in _CODE_SPAN.finditer(line):
        out.append(_escape_text(line[pos:m.start()]))
        out.append(m.group(0))  # kramdown escapes code span contents itself
        pos = m.end()
    out.append(_escape_text(line[pos:]))
    return "".join(out)


def sanitize_markdown(text):
    """Markdown from an issue body, made safe for Jekyll + kramdown.

    - Liquid: all `{{` / `{%` become literal text (everywhere, code included,
      because Liquid runs before Markdown).
    - HTML: `<` outside code becomes `&lt;`, so tags show as text.
    - kramdown `{:` attribute lists are disabled; link targets with schemes
      other than http/https/mailto are replaced by `#`.
    Code inside closed fences and inline code spans is left as written so it
    still displays correctly. When unsure, text is escaped (it may then show
    an `&lt;` literally, but can't inject markup).
    """
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        m = _FENCE_OPEN.match(lines[i])
        if m:
            fence = m.group(1)
            closer = re.compile(r"^ {0,3}" + re.escape(fence) + re.escape(fence[0]) + r"*\s*$")
            end = next((j for j in range(i + 1, len(lines)) if closer.match(lines[j])), None)
            if end is not None:
                out.extend(lines[i:end + 1])
                i = end + 1
                continue
        out.append(_escape_inline(lines[i]))
        i += 1
    return escape_liquid("\n".join(out))


# ------------------------------------------------------------------- URLs

def validate_url(raw):
    url = (raw or "").strip()
    if not url:
        raise InboxError("No URL given. Use a title like `save link: https://example.com/page`.")
    if re.search(r"[\s\x00-\x1f\x7f]", url):
        raise InboxError("The URL must not contain spaces or control characters.")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise InboxError("Only `http://` and `https://` URLs can be saved.")
    return url


def normalize_url(url):
    parts = urllib.parse.urlsplit(url.strip())
    path = parts.path.rstrip("/")
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


class _TitleParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.done = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "title" and not self.done:
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title" and self.in_title:
            self.in_title, self.done = False, True

    def handle_data(self, data):
        if self.in_title:
            self.parts.append(data)


class _HttpOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme.lower() not in ("http", "https"):
            raise urllib.error.URLError("redirect to a non-http(s) URL")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_title(url, timeout=FETCH_TIMEOUT, max_bytes=FETCH_MAX_BYTES):
    """Return the page's <title>, or None. Never raises."""
    try:
        deadline = time.monotonic() + timeout
        opener = urllib.request.build_opener(_HttpOnlyRedirects)
        req = urllib.request.Request(url, headers={"User-Agent": "til-inbox/1.0"})
        with opener.open(req, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if ctype and "html" not in ctype.lower():
                return None
            charset = resp.headers.get_content_charset() or "utf-8"
            data = b""
            while len(data) < max_bytes and time.monotonic() < deadline:
                chunk = resp.read(min(65536, max_bytes - len(data)))
                if not chunk:
                    break
                data += chunk
                if b"</title" in data.lower():
                    break
        parser = _TitleParser()
        parser.feed(data.decode(charset, errors="replace"))
        title = clean_line("".join(parser.parts))
        return title[:MAX_TITLE].strip() or None
    except Exception:
        return None


# ----------------------------------------------------------- reading list

def load_reading(root):
    path = Path(root) / READING_FILE
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise InboxError(f"`{READING_FILE}` is not a list; fix it by hand first.")
    for entry in data:
        # Hand-edited dates may load as date objects; keep everything as text.
        for key in ("added", "read"):
            if key in entry and not isinstance(entry[key], str):
                entry[key] = str(entry[key])
    return data


def dump_yaml(data):
    return yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000
    )


def atomic_write(root, relpath, text):
    """Write a file in one step (temp file + rename), only under allowed paths."""
    root = Path(root).resolve()
    target = (root / relpath).resolve()
    allowed = [root / READING_FILE, root / POSTS_DIR]
    if not (target == allowed[0] or target.parent == allowed[1]):
        raise InboxError("Refusing to write outside _data/reading.yml and _posts/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".inbox-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def entry_label(entry):
    issue = entry.get("issue")
    ref = f"#{issue}" if issue else "no issue"
    return f"- {code(entry.get('title', ''))} ({ref}) {code(entry.get('url', ''))}"


# -------------------------------------------------------------- site info

def site_base(root):
    try:
        cfg = yaml.safe_load((Path(root) / "_config.yml").read_text(encoding="utf-8")) or {}
    except OSError:
        cfg = {}
    return str(cfg.get("url", "")).rstrip("/") + "/" + str(cfg.get("baseurl", "")).strip("/")


# --------------------------------------------------------------- commands

def cmd_save(issue, arg, root, now, fetch):
    url = validate_url(arg)
    entries = load_reading(root)
    key = normalize_url(url)
    for entry in entries:
        if normalize_url(str(entry.get("url", ""))) == key:
            issue_ref = f" (from #{entry['issue']})" if entry.get("issue") else ""
            raise InboxError(
                f"Already saved{issue_ref}: {code(entry.get('title', url))}, "
                f"status {code(entry.get('status', ''))}. Nothing changed."
            )
    title = clean_line(fetch(url) or "")[:MAX_TITLE].strip() or url
    entries.append({
        "title": title,
        "url": url,
        "note": clean_body(issue.body),
        "added": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "to-read",
        "issue": issue.number,
    })
    atomic_write(root, READING_FILE, READING_HEADER + dump_yaml(entries))
    page = f"{site_base(root)}/reading/#to-read"
    return Result(
        "done",
        f"Saved {code(title)} to the reading list as **to-read**.\n\n"
        f"It will appear at {page} once GitHub Pages rebuilds.",
        f"Inbox: save link to reading list (#{issue.number})",
        [READING_FILE],
    )


def cmd_read(issue, arg, root, now, fetch):
    query = clean_line(arg)
    if not query:
        raise InboxError("Say what you read: `read: #12` or `read: part of the title`.")
    entries = load_reading(root)
    by_number = re.fullmatch(r"#(\d+)", query)
    if by_number:
        matches = [e for e in entries if str(e.get("issue")) == by_number.group(1)]
    else:
        q = query.lower()
        matches = [
            e for e in entries
            if q in str(e.get("title", "")).lower() or q in str(e.get("url", "")).lower()
        ]
    if len(matches) > 1:
        listing = "\n".join(entry_label(e) for e in matches)
        raise InboxError(
            f"{len(matches)} entries match {code(query)}; nothing changed. "
            f"Open a new issue with `read: #<issue>` for the one you meant:\n\n{listing}"
        )
    if not matches:
        q = query.lower().lstrip("#")
        ranked = sorted(
            entries,
            key=lambda e: difflib.SequenceMatcher(None, q, str(e.get("title", "")).lower()).ratio(),
            reverse=True,
        )[:3]
        listing = "\n".join(entry_label(e) for e in ranked) or "_The reading list is empty._"
        raise InboxError(f"Nothing in the reading list matches {code(query)}. Closest titles:\n\n{listing}")
    entry = matches[0]
    entry["status"] = "read"
    entry["read"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    note = clean_body(issue.body)
    if note:
        entry["note"] = note
    atomic_write(root, READING_FILE, READING_HEADER + dump_yaml(entries))
    page = f"{site_base(root)}/reading/#read"
    return Result(
        "done",
        f"Marked {code(entry.get('title', ''))} as **read**"
        f"{' and saved your note' if note else ''}.\n\n"
        f"It will appear at {page} once GitHub Pages rebuilds.",
        f"Inbox: mark reading-list entry as read (#{issue.number})",
        [READING_FILE],
    )


_TAGS_LINE = re.compile(r"^\s*tags\s*:\s*(.*?)\s*$", re.I)


def parse_tags(body):
    """Pull the first `Tags: a, b` line (outside code fences) out of the body."""
    lines = body.split("\n")
    fence = None
    for i, line in enumerate(lines):
        m = _FENCE_OPEN.match(line)
        if m:
            if fence is None:
                fence = m.group(1)
            elif line.strip().startswith(fence):
                fence = None
            continue
        if fence is None:
            t = _TAGS_LINE.match(line)
            if t:
                raw = re.split(r"[,\s]+", t.group(1).strip("[]"))
                tags = []
                for tag in raw:
                    tag = slugify(tag, "")[:MAX_TAG_LEN].strip("-")
                    if tag and tag not in tags:
                        tags.append(tag)
                rest = "\n".join(lines[:i] + lines[i + 1:]).strip()
                return tags[:MAX_TAGS], rest
    return [], body


def cmd_til(issue, arg, root, now, fetch):
    title = clean_line(arg)
    if not title:
        raise InboxError("The note needs a title: `TIL: what I learned`.")
    tags, content = parse_tags(clean_body(issue.body))
    if not content:
        raise InboxError("The issue body is empty; it becomes the note's content.")
    slug = slugify(title, f"note-{issue.number}")
    relpath = f"{POSTS_DIR}/{now:%Y-%m-%d}-{slug}.md"
    if (Path(root) / relpath).exists():
        raise InboxError(f"A note already exists at {code(relpath)}; pick a different title.")
    front = dump_yaml({"title": title, "tags": tags})
    atomic_write(root, relpath, f"---\n{front}---\n\n{sanitize_markdown(content)}\n")
    page = f"{site_base(root)}/{now:%Y/%m/%d}/{slug}/"
    return Result(
        "done",
        f"Created {code(relpath)} with tags {code(', '.join(tags) or 'none')}.\n\n"
        f"It will be live at {page} once GitHub Pages rebuilds.",
        f"Inbox: add TIL note {now:%Y-%m-%d}-{slug} (#{issue.number})",
        [relpath],
    )


HANDLERS = {"save": cmd_save, "read": cmd_read, "til": cmd_til}


def process(issue, owner, root, now=None, fetch=fetch_title):
    """Decide what to do with an issue; write files only on success."""
    if not owner or issue.author.lower() != owner.lower():
        return Result("ignored")
    command = None
    for name, pattern in COMMANDS:
        m = pattern.match(issue.title or "")
        if m:
            command, arg = name, m.group(1)
            break
    if command is None:
        return Result("ignored")
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        if len(issue.title) > MAX_TITLE:
            raise InboxError(f"The issue title is longer than {MAX_TITLE} characters.")
        if len(issue.body or "") > MAX_BODY:
            raise InboxError(f"The issue body is longer than {MAX_BODY} characters.")
        return HANDLERS[command](issue, arg, root, now, fetch)
    except InboxError as exc:
        return Result("error", str(exc))
    except Exception as exc:  # unexpected: report the type, not internals
        return Result("error", f"Unexpected error ({type(exc).__name__}); nothing was changed.")


# ------------------------------------------------- git + GitHub (CI only)

def run(*args, root, stdin=None):
    return subprocess.run(args, cwd=root, input=stdin, text=True, check=True,
                          capture_output=True)


def commit_and_push(result, root):
    run("git", "config", "user.name", "github-actions[bot]", root=root)
    run("git", "config", "user.email",
        "41898282+github-actions[bot]@users.noreply.github.com", root=root)
    run("git", "add", "--", *result.paths, root=root)
    run("git", "commit", "-F", "-", root=root, stdin=result.commit_message + "\n")
    for attempt in range(3):
        try:
            run("git", "push", "origin", "HEAD", root=root)
            return
        except subprocess.CalledProcessError:
            if attempt == 2:
                raise
            run("git", "pull", "--rebase", "origin",
                run("git", "rev-parse", "--abbrev-ref", "HEAD", root=root).stdout.strip(),
                root=root)


def gh_comment(number, body, root):
    footer = "\n\n<sub>Processed by the issue inbox workflow.</sub>"
    run("gh", "issue", "comment", str(number), "--body-file", "-", root=root, stdin=body + footer)


def main():
    env = os.environ
    root = env.get("GITHUB_WORKSPACE", os.getcwd())
    try:
        number = int(env.get("ISSUE_NUMBER", ""))
    except ValueError:
        print("ISSUE_NUMBER missing", file=sys.stderr)
        return 1
    issue = Issue(number, env.get("ISSUE_TITLE", ""), env.get("ISSUE_BODY", ""),
                  env.get("ISSUE_AUTHOR", ""))
    result = process(issue, env.get("REPO_OWNER", ""), root)
    print(f"inbox: issue #{number}: {result.status}")
    if result.status == "ignored":
        return 0
    if result.status == "done":
        try:
            commit_and_push(result, root)
        except subprocess.CalledProcessError as exc:
            print(exc.stderr, file=sys.stderr)
            subprocess.run(["git", "rebase", "--abort"], cwd=root, capture_output=True)
            subprocess.run(["git", "reset", "--hard", "@{upstream}"], cwd=root, capture_output=True)
            result = Result("error", "Could not commit or push the change; nothing was saved.")
    if result.status == "done":
        gh_comment(number, result.message, root)
        run("gh", "issue", "close", str(number), "--reason", "completed", root=root)
        return 0
    gh_comment(number, "Inbox error: " + result.message, root)
    return 0  # reported on the issue, which stays open


if __name__ == "__main__":
    sys.exit(main())
