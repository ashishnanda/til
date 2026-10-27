import datetime as dt
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inbox  # noqa: E402

OWNER = "ashishnanda"
NOW = dt.datetime(2026, 10, 27, 12, 30, tzinfo=dt.timezone.utc)


@pytest.fixture
def site(tmp_path):
    (tmp_path / "_config.yml").write_text(
        'url: "https://ashishnanda.github.io"\nbaseurl: "/til"\n'
    )
    (tmp_path / "_data").mkdir()
    (tmp_path / "_data/reading.yml").write_text("[]\n")
    (tmp_path / "_posts").mkdir()
    return tmp_path


def run(site, title, body="", author=OWNER, number=1, fetch=lambda url: "Page Title"):
    issue = inbox.Issue(number, title, body, author)
    return inbox.process(issue, OWNER, site, now=NOW, fetch=fetch)


def reading(site):
    return yaml.safe_load((site / "_data/reading.yml").read_text())


def snapshot(site):
    return {p.relative_to(site): p.read_bytes() for p in site.rglob("*") if p.is_file()}


# ------------------------------------------------------------ owner / routing

def test_non_owner_is_ignored_without_changes(site):
    before = snapshot(site)
    for title in ("save link: https://example.com", "TIL: x", "read: x"):
        result = run(site, title, "body", author="someone-else")
        assert result.status == "ignored"
        assert result.message == ""
    assert snapshot(site) == before


def test_owner_match_is_case_insensitive(site):
    assert run(site, "save link: https://example.com", author="AshishNanda").status == "done"


def test_other_titles_are_ignored(site):
    before = snapshot(site)
    for title in ("Bug: page broken", "saved link https://x.com", "reading list idea", "til without colon"):
        assert run(site, title).status == "ignored"
    assert snapshot(site) == before


@pytest.mark.parametrize("title", ["SAVE LINK: https://example.com", "Save Link:https://example.com",
                                   "  save   link : https://example.com"])
def test_prefix_is_case_insensitive(site, title):
    assert run(site, title).status == "done"


# ------------------------------------------------------------------ save link

def test_save_link_appends_entry(site):
    result = run(site, "save link: https://example.com/a", "Worth a look", number=7)
    assert result.status == "done"
    assert result.paths == ["_data/reading.yml"]
    assert "#7" in result.commit_message
    assert "https://ashishnanda.github.io/til/reading/" in result.message
    assert reading(site) == [{
        "title": "Page Title", "url": "https://example.com/a", "note": "Worth a look",
        "added": "2026-10-27T12:30:00Z", "status": "to-read", "issue": 7,
    }]


@pytest.mark.parametrize("url", ["ftp://example.com/x", "javascript:alert(1)", "file:///etc/passwd",
                                 "example.com", "https://", "http://exa mple.com", ""])
def test_save_link_rejects_invalid_urls(site, url):
    before = snapshot(site)
    result = run(site, f"save link: {url}")
    assert result.status == "error"
    assert snapshot(site) == before


def test_save_link_title_fetch_failure_uses_url(site):
    result = run(site, "save link: https://example.com/x", fetch=lambda url: None)
    assert result.status == "done"
    assert reading(site)[0]["title"] == "https://example.com/x"


def test_save_link_fetch_exception_uses_url(site, monkeypatch):
    def boom(*a, **k):
        raise TimeoutError("slow")
    monkeypatch.setattr(inbox.urllib.request.OpenerDirector, "open", boom)
    assert inbox.fetch_title("https://example.com") is None
    result = run(site, "save link: https://example.com/x", fetch=inbox.fetch_title)
    assert result.status == "done"
    assert reading(site)[0]["title"] == "https://example.com/x"


def test_fetch_title_parses_and_limits(monkeypatch):
    class Resp:
        def __init__(self, data):
            self.data, self.headers = data, __import__("email.message").message.Message()
            self.headers["Content-Type"] = "text/html; charset=utf-8"
            self.read_sizes = []

        def read(self, n):
            self.read_sizes.append(n)
            chunk, self.data = self.data[:n], self.data[n:]
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    resp = Resp(b"<html><head><title> Hello &amp;\n world </title></head>" + b"x" * 10_000_000)
    monkeypatch.setattr(inbox.urllib.request.OpenerDirector, "open", lambda *a, **k: resp)
    assert inbox.fetch_title("https://example.com") == "Hello & world"
    assert sum(resp.read_sizes) <= inbox.FETCH_MAX_BYTES

    big = Resp(b"<title>" + b"a" * 2_000_000 + b"</title>")
    monkeypatch.setattr(inbox.urllib.request.OpenerDirector, "open", lambda *a, **k: big)
    inbox.fetch_title("https://example.com", max_bytes=1000)
    assert sum(big.read_sizes) <= 1000


def test_save_link_duplicate_is_not_added(site):
    run(site, "save link: https://Example.com/a/", number=1)
    before = snapshot(site)
    result = run(site, "save link: https://example.com/a#section", number=2)
    assert result.status == "error"
    assert "Already saved" in result.message and "#1" in result.message
    assert snapshot(site) == before
    assert len(reading(site)) == 1


def test_save_link_yaml_special_characters_round_trip(site):
    title = "Quotes \"double\" 'single': colon # hash - [list] {map} & *star ! | > % @"
    note = "line one\n---\nkey: value\n- item\n'quoted' \"too\""
    result = run(site, "save link: https://example.com/?q=a:b&c='d'", note, fetch=lambda u: title)
    assert result.status == "done"
    entry = reading(site)[0]
    assert entry["title"] == title
    assert entry["note"] == note
    assert entry["url"] == "https://example.com/?q=a:b&c='d'"


def test_save_link_fetched_title_is_cleaned_and_truncated(site):
    run(site, "save link: https://example.com", fetch=lambda u: "a\x00b\n\tc" + "x" * 500)
    title = reading(site)[0]["title"]
    assert title.startswith("ab c") and len(title) <= inbox.MAX_TITLE


def test_save_preserves_existing_entries_and_header(site):
    (site / "_data/reading.yml").write_text(
        "- title: Old\n  url: https://old.example\n  added: 2026-01-01\n  status: read\n"
    )
    run(site, "save link: https://new.example")
    text = (site / "_data/reading.yml").read_text()
    assert text.startswith("# Reading list.")
    entries = reading(site)
    assert [e["title"] for e in entries] == ["Old", "Page Title"]
    assert entries[0]["added"] == "2026-01-01"


# ----------------------------------------------------------------------- read

@pytest.fixture
def stocked(site):
    titles = {
        "https://a.example/python-tips": "Python packaging tips",
        "https://b.example/rust": "Rust ownership explained",
        "https://c.example/py-async": "Async Python in depth",
    }
    for n, (url, title) in enumerate(titles.items(), start=10):
        assert run(site, f"save link: {url}", "why", number=n, fetch=lambda u, t=title: t).status == "done"
    return site


def test_read_by_issue_number(stocked):
    result = run(stocked, "read: #11", "Great read.", number=20)
    assert result.status == "done"
    entry = next(e for e in reading(stocked) if e["issue"] == 11)
    assert entry["status"] == "read"
    assert entry["read"] == "2026-10-27T12:30:00Z"
    assert entry["note"] == "Great read."
    assert "https://ashishnanda.github.io/til/reading/" in result.message


def test_read_unknown_issue_number_is_no_match(stocked):
    before = snapshot(stocked)
    result = run(stocked, "read: #99")
    assert result.status == "error" and "Closest titles" in result.message
    assert snapshot(stocked) == before


def test_read_single_partial_match_title_case_insensitive(stocked):
    assert run(stocked, "read: RUST own").status == "done"
    assert [e["status"] for e in reading(stocked)] == ["to-read", "read", "to-read"]


def test_read_single_match_on_url(stocked):
    assert run(stocked, "read: py-async").status == "done"
    assert reading(stocked)[2]["status"] == "read"


def test_read_empty_body_keeps_saved_note(stocked):
    run(stocked, "read: #10", "")
    assert reading(stocked)[0]["note"] == "why"


def test_read_multiple_matches_lists_them(stocked):
    before = snapshot(stocked)
    result = run(stocked, "read: python")
    assert result.status == "error"
    assert "2 entries match" in result.message
    assert "#10" in result.message and "#12" in result.message and "#11" not in result.message
    assert snapshot(stocked) == before


def test_read_no_match_suggests_three_closest(stocked):
    run(stocked, "save link: https://d.example", fetch=lambda u: "Gardening", number=13)
    before = snapshot(stocked)
    result = run(stocked, "read: Rust ownersip")  # typo
    assert result.status == "error"
    assert "Closest titles" in result.message
    listed = [line for line in result.message.splitlines() if line.startswith("- ")]
    assert len(listed) == 3
    assert "Rust ownership explained" in listed[0]
    assert snapshot(stocked) == before


def test_read_empty_query(stocked):
    assert run(stocked, "read:   ").status == "error"


# ------------------------------------------------------------------------ TIL

def post(site):
    files = list((site / "_posts").iterdir())
    assert len(files) == 1
    return files[0]


def front_matter(path):
    text = path.read_text()
    assert text.startswith("---\n")
    head, body = text[4:].split("\n---\n", 1)
    return yaml.safe_load(head), body


def test_til_creates_post_with_tags(site):
    body = "Use `git switch -`.\n\nTags: Git, CLI , git\n\nMore text."
    result = run(site, "TIL: Switching back with git switch -", body, number=5)
    assert result.status == "done"
    path = post(site)
    assert path.name == "2026-10-27-switching-back-with-git-switch.md"
    assert result.paths == ["_posts/2026-10-27-switching-back-with-git-switch.md"]
    fm, content = front_matter(path)
    assert fm == {"title": "Switching back with git switch -", "tags": ["git", "cli"]}
    assert "Tags:" not in content
    assert "Use `git switch -`." in content and "More text." in content
    assert "https://ashishnanda.github.io/til/2026/10/27/switching-back-with-git-switch/" in result.message


def test_til_without_tags_line(site):
    run(site, "TIL: Plain", "Just text.")
    assert front_matter(post(site))[0]["tags"] == []


@pytest.mark.parametrize("line,expected", [
    ("tags: python", ["python"]),
    ("TAGS: [git, github-pages]", ["git", "github-pages"]),
    ("Tags: C++, Node.js, ../../etc", ["c", "node-js", "etc"]),
    ("Tags: a b c", ["a", "b", "c"]),
])
def test_tag_parsing(line, expected):
    tags, rest = inbox.parse_tags(f"Intro\n{line}\nOutro")
    assert tags == expected
    assert rest == "Intro\nOutro"


def test_tags_line_inside_code_fence_is_kept(site):
    body = "```yaml\ntags: not-these\n```\nTags: real"
    run(site, "TIL: Fenced", body)
    fm, content = front_matter(post(site))
    assert fm["tags"] == ["real"]
    assert "tags: not-these" in content


def test_til_empty_body_rejected(site):
    assert run(site, "TIL: Nothing", "Tags: x").status == "error"
    assert list((site / "_posts").iterdir()) == []


def test_til_existing_file_not_overwritten(site):
    run(site, "TIL: Same", "one")
    before = snapshot(site)
    result = run(site, "TIL: Same", "two")
    assert result.status == "error"
    assert snapshot(site) == before


# ---------------------------------------------------------------------- slugs

@pytest.mark.parametrize("title,slug", [
    ("Hello, World!", "hello-world"),
    ("../../etc/passwd", "etc-passwd"),
    ("..\\..\\windows\\system32", "windows-system32"),
    ("Café déjà vu", "cafe-deja-vu"),
    ("UPPER_case and   spaces", "upper-case-and-spaces"),
    ("{% include x %} <script>", "include-x-script"),
    ("/absolute/path.md", "absolute-path-md"),
])
def test_slugify(title, slug):
    assert inbox.slugify(title, "fallback") == slug


def test_slug_length_and_charset():
    slug = inbox.slugify("word " * 40, "f")
    assert len(slug) <= 60 and not slug.endswith("-")
    assert set(slug) <= set("abcdefghijklmnopqrstuvwxyz0123456789-")
    assert len(inbox.slugify("x" * 100, "f")) == 60


def test_slug_fallback_for_symbol_only_title(site):
    result = run(site, "TIL: !!! ???", "body", number=42)
    assert result.status == "done"
    assert post(site).name == "2026-10-27-note-42.md"


def test_til_path_traversal_stays_in_posts(site):
    run(site, "TIL: ../../_config", "pwned")
    assert post(site).parent == site / "_posts"
    assert "pwned" not in (site / "_config.yml").read_text()


def test_atomic_write_refuses_other_paths(site):
    for rel in ("_config.yml", "_posts/../x.md", "_posts/sub/x.md", "_data/other.yml"):
        with pytest.raises(inbox.InboxError):
            inbox.atomic_write(site, rel, "x")


# ---------------------------------------------------------- injection / YAML

def test_til_title_yaml_and_liquid_special_characters(site):
    title = "Quotes \"x\" 'y': {{ site.title }} {% raw %} <script>alert(1)</script> --- # & *a"
    assert run(site, f"TIL: {title}", "body").status == "done"
    fm, _ = front_matter(post(site))
    assert fm["title"] == title  # stored verbatim; templates escape on output


def test_til_body_liquid_is_neutralised(site):
    body = "Liquid: {{ site.github }} and {% include evil.html %} and {%- endraw -%} and {{{x}}}"
    run(site, "TIL: Liquid", body)
    _, content = front_matter(post(site))
    stripped = content.replace('{{ "{" }}', "")
    assert "{{" not in stripped and "{%" not in stripped


def test_escape_liquid_never_leaves_a_live_tag():
    for text in ["{{", "{%", "{{{", "{{}}", "{%}", "{{ x }}}", "{ {", "{{%", "a{%b%}c"]:
        out = inbox.escape_liquid(text)
        assert out.replace('{{ "{" }}', "").count("{{") == 0
        assert "{%" not in out
        # A generated tag is never followed by "}" (which Liquid would swallow).
        assert '{{ "{" }}}' not in out


def test_til_body_html_is_escaped(site):
    body = ('<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n'
            '[click](javascript:alert(1)) [ok](https://example.com)\n'
            '[ent](java&#115;cript:alert(1))\n[ref]: javascript:alert(1)\n'
            'Para\n{: onclick="alert(1)"}\n{::nomarkdown}<b>x</b>{:/}')
    run(site, "TIL: XSS", body)
    _, content = front_matter(post(site))
    assert "<script" not in content and "<img" not in content and "<b>" not in content
    assert "javascript:" not in content and "java&#115;cript" not in content
    assert "](https://example.com)" in content
    assert "{:" not in content


def test_code_is_left_readable_but_liquid_still_escaped(site):
    body = "Inline `<div>` code.\n\n```html\n<p>{{ name }}</p>\n```\n\nAfter <b>."
    run(site, "TIL: Code", body)
    _, content = front_matter(post(site))
    assert "`<div>`" in content
    assert '<p>{{ "{" }}{ name }}</p>' in content
    assert "After &lt;b>." in content


def test_unclosed_fence_is_escaped(site):
    run(site, "TIL: Unclosed", "```\n<script>x</script>")
    _, content = front_matter(post(site))
    assert "<script" not in content


def test_escaped_backtick_is_not_code():
    assert "<b>" not in inbox.sanitize_markdown(r"\`<b>`")


# -------------------------------------------------------------- length limits

def test_title_too_long_rejected(site):
    before = snapshot(site)
    result = run(site, "TIL: " + "x" * 200, "body")
    assert result.status == "error" and "200" in result.message
    assert snapshot(site) == before


def test_body_too_long_rejected(site):
    before = snapshot(site)
    for title in ("TIL: ok", "save link: https://example.com", "read: x"):
        result = run(site, title, "x" * 5001)
        assert result.status == "error" and "5000" in result.message
    assert snapshot(site) == before


def test_limits_are_inclusive(site):
    title = "TIL: " + "x" * (200 - len("TIL: "))
    assert run(site, title, "y" * 5000).status == "done"


# --------------------------------------------------------------- error paths

def test_unexpected_error_reports_without_changes(site, monkeypatch):
    def broken(*a):
        raise RuntimeError("secret internals")
    monkeypatch.setattr(inbox, "dump_yaml", broken)
    before = snapshot(site)
    result = run(site, "save link: https://example.com")
    assert result.status == "error"
    assert "secret internals" not in result.message
    assert snapshot(site) == before


def test_corrupt_reading_file_reports_error(site):
    (site / "_data/reading.yml").write_text("key: value\n")
    assert run(site, "save link: https://example.com").status == "error"


def test_comment_code_span_handles_backticks_and_mentions():
    assert inbox.code("a ` b @user") == "`` a ` b @user ``"
