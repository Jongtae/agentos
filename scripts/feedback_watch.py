#!/usr/bin/env python3
"""File public mentions of Personal AgentOS as `feedback` issues (#1143, #1165).

Development infrastructure for the open-source project, not a product feature.
Run by .github/workflows/feedback-watch.yml.

Every source is filtered here by name, whatever the source claims to filter:
hnrss.org stopped honouring its search parameter and Reddit search returns
loose matches (#1165). At most MAX_NEW issues are created per run.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Iterable

NAME = re.compile(r"personal\s+agentos|jongtae/agentos", re.I)
MAX_NEW = 5
MARKER = "<!-- feedback-source: {url} -->"
MARKER_RE = re.compile(r"<!-- feedback-source: (\S+) -->")
USER_AGENT = "agentos-feedback-watch/1.0 (+https://github.com/Jongtae/agentos)"
ATOM = "{http://www.w3.org/2005/Atom}"

HN_QUERIES = ('"Personal AgentOS"', '"Jongtae/agentos"')
REDDIT_FEED = "https://www.reddit.com/search.rss?q=%22Personal+AgentOS%22+OR+%22Jongtae%2Fagentos%22&sort=new"
GEEKNEWS_FEED = "https://news.hada.io/rss/news"

Fetch = Callable[[str], bytes]


@dataclass(frozen=True)
class Mention:
    source: str
    url: str
    title: str
    text: str
    author: str
    created: str

    def matches(self) -> bool:
        return bool(NAME.search(" ".join((self.title, self.text, self.url))))


def plain(value: str | None) -> str:
    """Strip markup and collapse whitespace."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def http_fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def hacker_news(fetch: Fetch, since: int) -> list[Mention]:
    found = []
    for query in HN_QUERIES:
        params = urllib.parse.urlencode({
            "query": query, "tags": "(story,comment)",
            "numericFilters": f"created_at_i>{since}", "hitsPerPage": 50,
        })
        data = json.loads(fetch(f"https://hn.algolia.com/api/v1/search_by_date?{params}"))
        for hit in data.get("hits", []):
            is_comment = bool(hit.get("comment_text"))
            title = (f"Comment on \"{hit.get('story_title') or ''}\"" if is_comment
                     else hit.get("title") or hit.get("story_title") or "")
            text = " ".join(filter(None, (hit.get("comment_text"), hit.get("story_text"), hit.get("url"))))
            found.append(Mention("hn", f"https://news.ycombinator.com/item?id={hit['objectID']}",
                                 plain(title), plain(text), hit.get("author") or "", hit.get("created_at") or ""))
    return found


def atom_entries(source: str, body: bytes) -> list[Mention]:
    root = ET.fromstring(body)
    found = []
    for entry in root.iter(f"{ATOM}entry"):
        link = entry.find(f"{ATOM}link")
        url = (link.get("href") if link is not None else None) or (entry.findtext(f"{ATOM}id") or "")
        text = entry.findtext(f"{ATOM}content") or entry.findtext(f"{ATOM}summary") or ""
        author = entry.findtext(f"{ATOM}author/{ATOM}name") or ""
        created = entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated") or ""
        found.append(Mention(source, url.strip(), plain(entry.findtext(f"{ATOM}title")), plain(text), author, created))
    return found


def reddit(fetch: Fetch, since: int) -> list[Mention]:
    return atom_entries("reddit", fetch(REDDIT_FEED))


def geeknews(fetch: Fetch, since: int) -> list[Mention]:
    return atom_entries("geeknews", fetch(GEEKNEWS_FEED))


SOURCES = (hacker_news, reddit, geeknews)


def collect(fetch: Fetch, since: int, log: Callable[[str], None] = print) -> list[Mention]:
    """Matching mentions from every source; a failing source is logged and skipped."""
    mentions: dict[str, Mention] = {}
    for source in SOURCES:
        try:
            items = source(fetch, since)
        except Exception as exc:  # network refusals, parse errors
            log(f"{source.__name__}: skipped ({type(exc).__name__}: {exc})")
            continue
        kept = [item for item in items if item.url and item.matches()]
        log(f"{source.__name__}: {len(items)} items, {len(kept)} mention the project")
        for item in kept:
            mentions.setdefault(item.url, item)
    return list(mentions.values())


def issue_title(mention: Mention) -> str:
    return f"[feedback:{mention.source}] {mention.title or mention.url}"[:120]


def issue_body(mention: Mention) -> str:
    excerpt = mention.text[:600] + ("…" if len(mention.text) > 600 else "")
    return "\n".join([
        f"Public mention found by `feedback-watch` on **{mention.source}**.",
        "",
        f"- Link: {mention.url}",
        f"- Author: {mention.author or 'unknown'}",
        f"- Posted: {mention.created or 'unknown'}",
        "",
        "> " + (excerpt or "(no text)").replace("\n", "\n> "),
        "",
        "Triage adds a summary and a recommended action. Nothing here is acted on automatically.",
        "",
        MARKER.format(url=mention.url),
    ])


class GitHub:
    def __init__(self, token: str, repo: str, opener: Callable = urllib.request.urlopen):
        self.token, self.repo, self.opener = token, repo, opener

    def _call(self, method: str, path: str, payload: dict | None = None):
        request = urllib.request.Request(
            f"https://api.github.com/repos/{self.repo}{path}", method=method,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                     "User-Agent": USER_AGENT},
        )
        with self.opener(request, timeout=20) as response:
            return json.loads(response.read() or b"null")

    def known_sources(self) -> set[str]:
        known: set[str] = set()
        for page in range(1, 11):
            issues = self._call("GET", f"/issues?labels=feedback&state=all&per_page=100&page={page}")
            for issue in issues:
                known.update(MARKER_RE.findall(issue.get("body") or ""))
            if len(issues) < 100:
                break
        return known

    def create(self, mention: Mention) -> int:
        issue = self._call("POST", "/issues", {
            "title": issue_title(mention), "body": issue_body(mention),
            "labels": ["feedback", f"source:{mention.source}"],
        })
        return issue["number"]


def file_new(mentions: Iterable[Mention], github: GitHub | None, known: set[str], dry_run: bool,
             log: Callable[[str], None] = print) -> list[Mention]:
    new = [m for m in mentions if m.url not in known]
    if len(new) > MAX_NEW:
        log(f"{len(new)} new mentions; filing the first {MAX_NEW}, the rest wait for the next run")
        new = new[:MAX_NEW]
    for mention in new:
        if dry_run or github is None:
            log(f"would file: {issue_title(mention)} ({mention.url})")
        else:
            log(f"filed #{github.create(mention)}: {issue_title(mention)}")
    return new


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="list what would be filed; create nothing")
    parser.add_argument("--since-hours", type=int, default=96)
    args = parser.parse_args(argv)
    since = int(time.time()) - args.since_hours * 3600
    mentions = collect(http_fetch, since)
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY", "Jongtae/agentos")
    github = GitHub(token, repo) if token else None
    known = github.known_sources() if github else set()
    file_new(mentions, github, known, dry_run=args.dry_run or github is None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
