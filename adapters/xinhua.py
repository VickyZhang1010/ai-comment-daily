# -*- coding: utf-8 -*-
"""新华网：新华时评 / 新华社评论员 / 新华网评。

文章 URL 形如 news.cn/{channel}/20261109/{hash}/c.html，日期在路径中。
注意：新华网评有大量"组图"海报型内容，正文极短，直接排除。
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from adapters.base import Source, register

PAGES = [
    ("https://www.news.cn/depthobserve/xhsp.html", "新华时评", 40),
    ("https://www.news.cn/depthobserve/xhsply.html", "新华社评论员", 40),
    ("https://www.news.cn/comments/index.htm", "新华网评", 20),
]
DATE_RE = re.compile(r"/(20\d{6})/")
ARTICLE_RE = re.compile(r"/c\.html$")
SKIP_WORDS = ("组图", "图集", "海报", "视频", "直播", "图解", "H5")


@register
class Xinhua(Source):
    key = "xinhua"
    name = "新华网"
    priority = 95

    def list_articles(self, fetcher, date_str, rate):
        target = date_str.replace("-", "")
        found = {}
        for page, channel, limit in PAGES:
            html = fetcher.get_optional(page, rate=rate)
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            count = 0
            for a in soup.find_all("a", href=True):
                absolute = urljoin(page, a["href"].strip())
                if not ARTICLE_RE.search(absolute):
                    continue
                m = DATE_RE.search(absolute)
                if not m or m.group(1) != target:
                    continue
                title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
                if len(title) < 8 or any(w in title for w in SKIP_WORDS):
                    continue
                found[absolute] = {"url": absolute, "title": title, "channel": channel}
                count += 1
                if count >= limit:
                    break
        return list(found.values())
