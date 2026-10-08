import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("feedback_watch", ROOT / "scripts" / "feedback_watch.py")
watch = importlib.util.module_from_spec(SPEC)
sys.modules["feedback_watch"] = watch
SPEC.loader.exec_module(watch)


def atom(*entries):
    body = "".join(
        f'<entry><title>{title}</title><link href="{url}"/><content type="html">{text}</content>'
        f"<author><name>someone</name></author><updated>2026-10-08T00:00:00Z</updated></entry>"
        for title, url, text in entries
    )
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{body}</feed>'.encode()


def hn(*hits):
    return json.dumps({"hits": [dict(objectID=str(i), author="a", created_at="2026-10-08", **hit)
                                for i, hit in enumerate(hits)]}).encode()


def fetcher(hn_body=b'{"hits": []}', reddit_body=None, geeknews_body=None):
    def fetch(url):
        if "algolia" in url:
            return hn_body
        if "reddit" in url:
            if isinstance(reddit_body, Exception):
                raise reddit_body
            return reddit_body or atom()
        return geeknews_body or atom()
    return fetch


class FakeGitHub:
    def __init__(self):
        self.created = []

    def create(self, mention):
        self.created.append(mention)
        return len(self.created)


class FeedbackWatchTests(unittest.TestCase):
    def setUp(self):
        self.log = []

    def collect(self, fetch):
        return watch.collect(fetch, since=0, log=self.log.append)

    def test_unrelated_items_from_every_source_file_nothing(self):
        # #1165: hnrss returned the newest 20 comments regardless of the query.
        unrelated_hn = hn(*[{"comment_text": f"Rust port comment {i}", "story_title": "Rust Port of TypeScript"}
                            for i in range(20)])
        unrelated_reddit = atom(("Multi Agent Systems Look Scary", "https://reddit.com/r/x/1", "AgentOS-like ideas"))
        mentions = self.collect(fetcher(unrelated_hn, unrelated_reddit))
        github = FakeGitHub()
        filed = watch.file_new(mentions, github, set(), dry_run=False, log=self.log.append)
        self.assertEqual(filed, [])
        self.assertEqual(github.created, [])

    def test_name_in_title_text_or_url_is_a_mention(self):
        mentions = self.collect(fetcher(
            hn({"title": "Show HN: Personal AgentOS"},
               {"comment_text": "I tried github.com/Jongtae/agentos last night", "story_title": "Ask HN"}),
            atom(("Look at this", "https://github.com/Jongtae/agentos", "")),
            atom(("Show GN: Personal AgentOS - 개인 에이전트", "https://news.hada.io/topic?id=1", "본문")),
        ))
        self.assertEqual({m.source for m in mentions}, {"hn", "reddit", "geeknews"})
        self.assertEqual(len(mentions), 4)

    def test_known_source_is_not_filed_again(self):
        mentions = self.collect(fetcher(hn({"title": "Personal AgentOS"})))
        github = FakeGitHub()
        watch.file_new(mentions, github, {mentions[0].url}, dry_run=False, log=self.log.append)
        self.assertEqual(github.created, [])

    def test_body_carries_the_dedupe_marker(self):
        mention = self.collect(fetcher(hn({"title": "Personal AgentOS"})))[0]
        self.assertEqual(watch.MARKER_RE.findall(watch.issue_body(mention)), [mention.url])

    def test_each_run_files_at_most_the_cap(self):
        many = hn(*[{"title": f"Personal AgentOS post {i}"} for i in range(12)])
        github = FakeGitHub()
        watch.file_new(self.collect(fetcher(many)), github, set(), dry_run=False, log=self.log.append)
        self.assertEqual(len(github.created), watch.MAX_NEW)

    def test_a_failing_source_does_not_stop_the_others(self):
        mentions = self.collect(fetcher(hn({"title": "Personal AgentOS"}), reddit_body=OSError("403")))
        self.assertEqual([m.source for m in mentions], ["hn"])
        self.assertTrue(any("reddit: skipped" in line for line in self.log))

    def test_dry_run_creates_nothing(self):
        github = FakeGitHub()
        filed = watch.file_new(self.collect(fetcher(hn({"title": "Personal AgentOS"}))), github, set(),
                               dry_run=True, log=self.log.append)
        self.assertEqual(len(filed), 1)
        self.assertEqual(github.created, [])


if __name__ == "__main__":
    unittest.main()
