# -*- coding: utf-8 -*-
"""金融・経済ニュース自動収集スクリプト

信頼できる大手メディア・公的機関の公式RSSのみを収集元とし、
金融・経済に関連する記事だけを docs/data.json に出力する。
標準ライブラリのみで動作する(追加インストール不要)。
"""
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

JST = timezone(timedelta(hours=9))
OUTPUT = Path(__file__).parent / "docs" / "data.json"

# 収集元の定義。official な RSS のみ。
# keyword_filter=True のフィードはビジネス以外の記事(自己啓発等)も含むため、
# 金融・経済キーワードに一致する記事だけを採用する。
FEEDS = [
    {"name": "NHK 経済", "url": "https://www3.nhk.or.jp/rss/news/cat5.xml",
     "category": "報道機関", "keyword_filter": False},
    {"name": "朝日新聞 経済", "url": "https://www.asahi.com/rss/asahi/business.rdf",
     "category": "報道機関", "keyword_filter": False},
    {"name": "時事通信", "url": "https://www.jiji.com/rss/ranking.rdf",
     "category": "報道機関", "keyword_filter": True},
    # ロイターは公式RSSを廃止済みのため、Google News RSS 経由で
    # jp.reuters.com の記事のみを取得する(リンク先はロイター本体の記事)
    {"name": "ロイター",
     "url": "https://news.google.com/rss/search?q=site:jp.reuters.com%20when:3d&hl=ja&gl=JP&ceid=JP:ja",
     "category": "報道機関", "keyword_filter": True, "strip_suffix": " - Reuters"},
    {"name": "東洋経済オンライン", "url": "https://toyokeizai.net/list/feed/rss",
     "category": "経済専門メディア", "keyword_filter": True},
    {"name": "ITmedia ビジネス", "url": "https://rss.itmedia.co.jp/rss/2.0/business.xml",
     "category": "経済専門メディア", "keyword_filter": True},
    {"name": "Yahoo!経済トピックス", "url": "https://news.yahoo.co.jp/rss/topics/business.xml",
     "category": "編集部厳選", "keyword_filter": False},
    {"name": "日本銀行", "url": "https://www.boj.or.jp/rss/whatsnew.xml",
     "category": "公的機関", "keyword_filter": False},
    {"name": "財務省", "url": "https://www.mof.go.jp/news.rss",
     "category": "公的機関", "keyword_filter": False},
    {"name": "金融庁", "url": "https://www.fsa.go.jp/fsaNewsListAll_rss2.xml",
     "category": "公的機関", "keyword_filter": False},
    # 経済産業省 (meti.go.jp) は海外IPからタイムアウトするため除外
    # (GitHub Actions のランナーは米国にあり毎回取得失敗する)
    # --- 海外の主要金融メディア (英語記事は収集時に日本語訳する) ---
    {"name": "CNBC", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
     "category": "海外金融", "keyword_filter": False, "lang": "en", "max": 8},
    {"name": "MarketWatch", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
     "category": "海外金融", "keyword_filter": False, "lang": "en", "max": 8},
    {"name": "WSJ マーケット", "url": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
     "category": "海外金融", "keyword_filter": False, "lang": "en", "max": 8},
    {"name": "Financial Times", "url": "https://www.ft.com/rss/home",
     "category": "海外金融", "keyword_filter": False, "lang": "en", "max": 8},
    # Bloomberg は公式RSSがなく、Google News 経由やサイトマップも
    # bot対策で取得不能のため見送り(主要記事は Yahoo!経済トピックス経由で入る)
]

# 金融・経済関連の判定キーワード
KEYWORDS = [
    "株", "円安", "円高", "為替", "ドル", "ユーロ", "金利", "利上げ", "利下げ",
    "日銀", "日本銀行", "FRB", "ECB", "中央銀行", "インフレ", "デフレ", "物価",
    "GDP", "景気", "経済", "市場", "相場", "投資", "証券", "債券", "国債",
    "決算", "業績", "財政", "税", "予算", "賃金", "賃上げ", "雇用", "失業",
    "貿易", "関税", "輸出", "輸入", "原油", "金融", "銀行", "融資", "ローン",
    "地価", "不動産", "暗号資産", "ビットコイン", "日経平均", "TOPIX",
    "ダウ", "ナスダック", "IPO", "上場", "買収", "M&A", "倒産", "値上げ",
    "消費", "小売", "企業", "産業", "NISA", "年金", "保険", "資産",
]

MAX_PER_SOURCE = 15   # 1ソースが一覧を占有しないよう上限を設ける
MAX_AGE_HOURS = 72    # 直近72時間の記事のみ
MAX_TOTAL = 150
MAX_TRANSLATE_CALLS = 80  # 1回の実行あたりの翻訳リクエスト上限(過負荷防止)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(item, name: str) -> str:
    for el in item.iter():
        if local_name(el.tag) == name and el.text:
            return el.text.strip()
    return ""


def parse_date(item) -> datetime | None:
    """pubDate (RFC822) / dc:date・updated・published (ISO8601) を JST に変換"""
    raw = child_text(item, "pubDate")
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(JST)
        except (ValueError, TypeError):
            pass
    for name in ("date", "published", "updated"):
        raw = child_text(item, name)
        if raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(JST)
            except ValueError:
                continue
    return None


def item_link(item) -> str:
    """RSS の <link>テキスト、または Atom の <link href="..."/> を取得"""
    for el in item.iter():
        if local_name(el.tag) != "link":
            continue
        if el.text and el.text.strip():
            return el.text.strip()
        if el.get("href"):
            return el.get("href")
    return ""


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def normalize_title(title: str) -> str:
    """重複判定用にタイトルを正規化(空白・記号を除去)"""
    return re.sub(r"[\s　、。・「」『』【】()（）:：!！?？…-]", "", title)


def is_finance_related(text: str) -> bool:
    return any(kw in text for kw in KEYWORDS)


def fetch_feed(feed: dict, now: datetime) -> list[dict]:
    req = urllib.request.Request(
        feed["url"], headers={"User-Agent": "Mozilla/5.0 (finance-news-collector)"})
    # 海外IPからだと応答が遅いサイトがあるため、失敗時は1回リトライする
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                root = ET.fromstring(res.read())
            break
        except Exception:
            if attempt == 1:
                raise

    if local_name(root.tag) == "html":
        raise ValueError("RSSではなくHTMLページが返されました(フィード廃止の可能性)")

    items = []
    cutoff = now - timedelta(hours=MAX_AGE_HOURS)
    for el in root.iter():
        if local_name(el.tag) not in ("item", "entry"):
            continue
        title = child_text(el, "title")
        link = item_link(el)
        if not title or not link:
            continue
        suffix = feed.get("strip_suffix")
        if suffix and title.endswith(suffix):
            title = title[: -len(suffix)].rstrip()
        if feed.get("strip_regex"):
            title = re.sub(feed["strip_regex"], "", title)
        summary = strip_html(
            child_text(el, "description") or child_text(el, "summary"))[:200]
        if feed["keyword_filter"] and not is_finance_related(title + summary):
            continue
        published = parse_date(el)
        if published and published < cutoff:
            continue
        items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "source": feed["name"],
            "category": feed["category"],
            "published": published.isoformat() if published else None,
            **({"lang": "en"} if feed.get("lang") == "en" else {}),
        })
    # フィードによっては日付順に並んでいないため、新しい順に揃えてから上限を適用
    items.sort(key=lambda x: x["published"] or "", reverse=True)
    return items[:feed.get("max", MAX_PER_SOURCE)]


def translate_ja(text: str) -> str | None:
    """Google翻訳の無料エンドポイントで英語→日本語に翻訳する"""
    params = urllib.parse.urlencode(
        {"client": "gtx", "sl": "en", "tl": "ja", "dt": "t", "q": text})
    req = urllib.request.Request(
        f"https://translate.googleapis.com/translate_a/single?{params}",
        headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as res:
        data = json.loads(res.read())
    return "".join(seg[0] for seg in data[0] if seg and seg[0]) or None


def load_translation_cache() -> dict:
    """前回の data.json から翻訳済み記事を読み込み、再翻訳を避ける"""
    cache = {}
    if OUTPUT.exists():
        try:
            for it in json.loads(OUTPUT.read_text(encoding="utf-8")).get("items", []):
                if it.get("title_orig"):
                    cache[it["link"]] = it
        except Exception:
            pass
    return cache


def translate_items(items: list[dict]) -> None:
    """英語記事のタイトル・要約を日本語訳する(失敗時は英語のまま表示)"""
    cache = load_translation_cache()
    calls = 0
    for item in items:
        if item.get("lang") != "en":
            continue
        cached = cache.get(item["link"])
        if cached:
            item["title_orig"] = cached["title_orig"]
            item["title"] = cached["title"]
            item["summary"] = cached.get("summary", item["summary"])
            continue
        if calls >= MAX_TRANSLATE_CALLS:
            continue  # 上限超過分は次回実行時に翻訳される
        try:
            translated = translate_ja(item["title"])
            calls += 1
            if translated:
                item["title_orig"] = item["title"]
                item["title"] = translated
            if item["summary"]:
                summary_ja = translate_ja(item["summary"][:150])
                calls += 1
                if summary_ja:
                    item["summary"] = summary_ja
            time.sleep(0.2)
        except Exception:
            pass


def main() -> None:
    now = datetime.now(JST)
    all_items = []
    errors = []
    for feed in FEEDS:
        try:
            items = fetch_feed(feed, now)
            all_items.extend(items)
            print(f"  {feed['name']}: {len(items)} 件")
        except Exception as e:  # 1フィードの失敗で全体を止めない
            errors.append(f"{feed['name']}: {e}")
            print(f"  {feed['name']}: 取得失敗 ({e})")

    # 重複排除(正規化タイトルが同一のものは先勝ち)
    seen = set()
    unique = []
    for item in sorted(all_items, key=lambda x: x["published"] or "", reverse=True):
        key = normalize_title(item["title"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    unique = unique[:MAX_TOTAL]
    translate_items(unique)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "generated_at": now.isoformat(),
        "sources": [{"name": f["name"], "category": f["category"]} for f in FEEDS],
        "errors": errors,
        "items": unique,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"合計 {len(unique)} 件を {OUTPUT} に出力しました")


if __name__ == "__main__":
    main()
