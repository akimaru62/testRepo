#!/usr/bin/env python3
"""
Fetch multiple RSS/Atom feeds (including hnrss frontpage) and merge results
into docs/data.json used by the static client.

Usage:
  pip install requests feedparser
  python scripts/fetch_feeds.py

This script performs server-side fetching to avoid CORS issues in the browser.
"""
import os
import re
import json
import time
from datetime import datetime, timezone
import requests
import feedparser
from email.utils import parsedate_to_datetime


FEEDS = [
    # (feed_url, source_name, category)
    ("https://hnrss.org/frontpage", "Hacker News", "テクノロジー"),
    ("https://aws.amazon.com/blogs/aws/feed/", "AWS ブログ (AWS)", "テクノロジー"),
    ("https://aws.amazon.com/blogs/architecture/feed/", "AWS ブログ (アーキテクチャ)", "開発者向け"),
    ("https://azure.microsoft.com/ja-jp/blog/feed/", "Azure ブログ", "テクノロジー"),
    ("https://azure.microsoft.com/updates/feed/", "Azure 更新情報", "テクノロジー"),
    ("https://github.blog/feed/", "GitHub Blog", "開発者向け"),
    ("https://cloud.google.com/blog/rss", "Google Cloud Blog", "テクノロジー"),
    # 以下は金融・経済系フィード（fetch_news.py の FEEDS と同等）
    ("https://www3.nhk.or.jp/rss/news/cat5.xml", "NHK 経済", "報道機関"),
    ("https://www.asahi.com/rss/asahi/business.rdf", "朝日新聞 経済", "報道機関"),
    ("https://www.jiji.com/rss/ranking.rdf", "時事通信", "報道機関"),
    ("https://news.google.com/rss/search?q=site:jp.reuters.com%20when:3d&hl=ja&gl=JP&ceid=JP:ja", "ロイター", "報道機関"),
    ("https://toyokeizai.net/list/feed/rss", "東洋経済オンライン", "経済専門メディア"),
    ("https://rss.itmedia.co.jp/rss/2.0/business.xml", "ITmedia ビジネス", "経済専門メディア"),
    ("https://news.yahoo.co.jp/rss/topics/business.xml", "Yahoo!経済トピックス", "編集部厳選"),
    ("https://www.boj.or.jp/rss/whatsnew.xml", "日本銀行", "公的機関"),
    ("https://www.mof.go.jp/news.rss", "財務省", "公的機関"),
    ("https://www.fsa.go.jp/fsaNewsListAll_rss2.xml", "金融庁", "公的機関"),
    ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "CNBC", "海外金融"),
    ("https://feeds.content.dowjones.io/public/rss/mw_topstories", "MarketWatch", "海外金融"),
    ("https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "WSJ マーケット", "海外金融"),
    ("https://www.ft.com/rss/home", "Financial Times", "海外金融"),
]


def norm_title(t: str) -> str:
    if not t:
        return ""
    # remove whitespace and common punctuation (similar to the JS normTitle)
    return re.sub(r"[\s　、。・「」『』【】()（）:：!！?？…\-]", "", t)


def parse_published(entry):
    # prefer published, then updated
    for key in ("published", "updated", "pubDate"):
        if key in entry and entry[key]:
            try:
                dt = parsedate_to_datetime(entry[key])
                if not dt.tzinfo:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                try:
                    # feedparser provides published_parsed
                    if entry.get("published_parsed"):
                        t = time.mktime(entry.published_parsed)
                        return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
                except Exception:
                    pass
    # fallback: now
    return datetime.now(timezone.utc).isoformat()


def strip_html(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"<[^>]+>", "", s).strip()


def load_existing(path):
    if not os.path.exists(path):
        return {"generated_at": None, "sources": [], "items": [], "errors": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    repo_root = os.path.dirname(os.path.dirname(__file__))
    data_path = os.path.join(repo_root, "docs", "data.json")
    data = load_existing(data_path)
    items = data.get("items", [])
    known = set(norm_title(i.get("title", "")) for i in items)

    added = 0
    for url, source, category in FEEDS:
        try:
            print(f"fetching {url} ...")
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                title = entry.get("title") or entry.get("summary") or ""
                link = entry.get("link") or entry.get("id") or ""
                if not title or not link:
                    continue
                n = norm_title(title)
                if n in known:
                    continue
                published = parse_published(entry)
                summary = strip_html(entry.get("summary", entry.get("description", "")))
                item = {
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "source": source,
                    "category": category,
                    "published": published,
                }
                items.append(item)
                known.add(n)
                added += 1
        except Exception as e:
            print(f"error fetching {url}: {e}")
            data.setdefault("errors", []).append({"url": url, "error": str(e)})

    # sort by published desc
    items.sort(key=lambda x: x.get("published") or "", reverse=True)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": data.get("sources", []),
        "errors": data.get("errors", []),
        "items": items,
    }
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"done. added {added} items, total {len(items)} items -> {data_path}")


if __name__ == "__main__":
    main()
