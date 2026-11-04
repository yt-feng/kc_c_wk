from __future__ import annotations

import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from crypto_observer import sources


END = datetime.fromisoformat("2026-11-04T18:00:00+08:00")
START = END - timedelta(days=7)
BODY = "The crypto company announced a blockchain settlement protocol upgrade for institutional digital assets. " * 12


def rss_item(title: str, url: str, date: str = "Wed, 04 Nov 2026 09:00:00 GMT", content: str = "") -> str:
    return f"<item><title>{title}</title><link>{url}</link><pubDate>{date}</pubDate><description>Crypto news</description><content:encoded><![CDATA[{content}]]></content:encoded></item>"


def rss(items: str) -> str:
    return f'<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>{items}</channel></rss>'


def raw(title: str, url: str, body: str = "") -> sources.RawItem:
    return sources.RawItem(title, url, "Publisher", "https://publisher.test/feed", END.isoformat(), article_text=body)


class FeedTests(unittest.TestCase):
    def parse(self, xml: str) -> list[sources.RawItem]:
        return sources.parse_rss(xml, "feed", START, END, "Publisher", "https://publisher.test/feed", "")

    def test_rss_enforces_publication_window_and_language(self):
        xml = rss(
            rss_item("Crypto fresh", "https://publisher.test/fresh?utm_source=rss#top", content=BODY)
            + rss_item("Crypto old", "https://publisher.test/old", "Wed, 21 Oct 2026 09:00:00 GMT")
            + rss_item("Crypto future", "https://publisher.test/future", "Wed, 11 Nov 2026 09:00:00 GMT")
            + rss_item("Crypto missing", "https://publisher.test/missing", "")
            + rss_item("中文 Crypto", "https://publisher.test/chinese")
        )
        items = self.parse(xml)
        self.assertEqual([item.title for item in items], ["Crypto fresh"])
        self.assertEqual(items[0].url, "https://publisher.test/fresh")
        self.assertEqual(items[0].published_at, "2026-11-04T17:00:00+08:00")
        self.assertEqual(items[0].article_text, BODY.strip())

    def test_atom_uses_published_date_and_alternate_article_link(self):
        xml = f'''<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><title>Crypto protocol launch</title><link rel="self" href="/api/1"/>
            <link rel="alternate" href="/news/1"/><published>2026-11-04T09:00:00Z</published>
            <updated>2026-11-04T09:30:00Z</updated><content type="html">{BODY}</content></entry>
          <entry><title>Crypto old updated</title><link href="/news/2"/>
            <published>2026-01-01T00:00:00Z</published><updated>2026-11-04T09:30:00Z</updated></entry>
          <entry><title>Crypto no publication</title><link href="/news/3"/>
            <updated>2026-11-04T09:30:00Z</updated></entry>
        </feed>'''
        items = self.parse(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://publisher.test/news/1")
        self.assertEqual(items[0].published_at, "2026-11-04T17:00:00+08:00")
        self.assertEqual(items[0].article_text, BODY.strip())

    def test_rss_accepts_namespaced_publication_date(self):
        xml = '''<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item>
          <title>Crypto fresh</title><link>https://publisher.test/news</link>
          <dc:date>2026-11-04T09:00:00Z</dc:date></item></channel></rss>'''
        self.assertEqual(len(self.parse(xml)), 1)

    def test_bing_link_resolves_to_allowed_publisher(self):
        xml = rss(rss_item("Bitcoin source", "https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fpublisher.test%2Fnews%3Futm_source%3Dbing"))
        self.assertEqual(self.parse(xml)[0].url, "https://publisher.test/news")
        blocked = "https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fmsn.com%2Fnews"
        self.assertFalse(sources.is_final_url_allowed(sources._publisher_link(blocked)))

    def test_feed_body_requires_same_publisher_and_strict_content(self):
        xml = rss(rss_item("Crypto syndicated", "https://other.test/article", content=BODY)
                  + rss_item("Crypto short", "https://publisher.test/short", content="crypto summary")
                  + rss_item("Crypto licence", "https://publisher.test/licence", content=BODY + " MIT license"))
        self.assertTrue(all(not item.article_text for item in self.parse(xml)))

    def test_invalid_feed_does_not_abort_discovery(self):
        with self.assertLogs(sources.LOGGER, level="WARNING"):
            self.assertEqual(self.parse("<html>not a feed"), [])


class DiscoveryTests(unittest.TestCase):
    def test_direct_feed_filters_non_crypto_and_biography(self):
        xml = rss(rss_item("Bitcoin regulation", "https://publisher.test/news", content=BODY)
                  + rss_item("Football update", "https://publisher.test/sports").replace("Crypto news", "sports")
                  + rss_item("Crypto chairman", "https://publisher.test/About/Commissioners/chairman", content=BODY))
        with patch.object(sources, "request_text", return_value=xml):
            items = sources.fetch_direct_feed("Publisher", "https://publisher.test/feed", START, END)
        self.assertEqual([item.title for item in items], ["Bitcoin regulation"])

    def test_direct_feed_remains_available_when_search_returns_no_items(self):
        xml = rss(rss_item("Bitcoin regulation", "https://publisher.test/news", content=BODY))
        with patch.multiple(sources, DIRECT_FEEDS={"Publisher": "https://publisher.test/feed"}, SECTION_QUERIES={"政策风向": ("crypto query",)}, TRACKED_SITES={}), \
             patch.object(sources, "window", return_value=(START, END)), \
             patch.object(sources, "request_text", return_value=xml), \
             patch.object(sources, "fetch_google", return_value=[]), \
             patch.object(sources, "fetch_bing", return_value=[]), \
             patch.object(sources, "fetch_gdelt", return_value=[]), \
             patch.object(sources, "fetch_article_text", return_value=("", "https://publisher.test/news", "")), \
             self.assertLogs(sources.LOGGER, level="INFO") as logs:
            items, warnings = sources.collect()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].article_text, BODY.strip())
        self.assertIn("verified=1", warnings[0])
        self.assertTrue(any("Discovery counts by source" in line for line in logs.output))

    def test_publisher_candidate_is_not_displaced_by_wrapper_limit(self):
        publisher = raw("Bitcoin source", "https://publisher.test/news", BODY)
        publisher.published_at = (END - timedelta(days=1)).isoformat()
        wrappers = [raw(f"Crypto wrapper {i}", f"https://news.google.com/rss/articles/{i}") for i in range(5)]
        with patch.multiple(sources, DIRECT_FEEDS={"Publisher": "https://publisher.test/feed"}, SECTION_QUERIES={}, TRACKED_SITES={"site": "crypto query"}), \
             patch.object(sources, "window", return_value=(START, END)), \
             patch.object(sources, "fetch_direct_feed", return_value=[publisher]), \
             patch.object(sources, "fetch_google", return_value=wrappers), \
             patch.object(sources, "fetch_bing", return_value=[]), \
             patch.object(sources, "fetch_gdelt", return_value=[]), \
             patch.object(sources, "fetch_article_text", return_value=(BODY, publisher.url, "Publisher")) as fetch:
            items, _ = sources.collect(max_items=1)
        self.assertEqual([item.url for item in items], [publisher.url])
        fetch.assert_called_once_with(publisher.url)

    def test_dedupe_replaces_wrapper_and_deduplicates_original_url(self):
        wrapper = raw("Bitcoin source", "https://news.google.com/rss/articles/id")
        publisher = raw("Bitcoin source", "https://publisher.test/news?utm_source=rss", BODY)
        retitled = raw("Bitcoin original title", "https://publisher.test/news")
        items = sources.dedupe([wrapper, publisher, retitled])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].article_text, BODY)
        self.assertTrue(sources.is_final_url_allowed(items[0].url))

    def test_article_container_is_preferred_over_page_licence_noise(self):
        html = f"<html><nav>Navigation</nav><article><p>{BODY}</p></article><div>MIT license</div></html>"
        response = unittest.mock.Mock(url="https://publisher.test/news", text=html, headers={"content-type": "text/html"})
        with patch.object(sources.requests, "get", return_value=response):
            text, url, _ = sources.fetch_article_text(response.url)
        self.assertEqual(text, BODY.strip())
        self.assertEqual(url, response.url)

    def test_enrichment_uses_bounded_concurrency_and_preserves_order(self):
        active = maximum = 0
        lock = threading.Lock()

        def fetch(url):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return BODY, url, "Publisher"

        inputs = [raw(f"Bitcoin article {i}", f"https://publisher.test/{i}") for i in range(12)]
        with patch.object(sources, "fetch_article_text", side_effect=fetch):
            items = sources.enrich_articles(inputs)
        self.assertGreater(maximum, 1)
        self.assertLessEqual(maximum, sources.ARTICLE_WORKERS)
        self.assertEqual([item.url for item in items], [item.url for item in inputs])


if __name__ == "__main__":
    unittest.main()
