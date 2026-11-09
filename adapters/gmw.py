# -*- coding: utf-8 -*-
"""光明日报：光明观察（时评）+ 评论员专栏。静态 HTML。"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from adapters.base import Source, register

PAGES = [
    ("https://guancha.gmw.cn/", "光明时评"),
    ("https://guancha.gmw.cn/node_40479.htm", "评论员专栏"),
]
DATE_RE = re.compile(r"/(\d{4})-(\d{2})/(\d{2})/content_\d+\.htm")


@register
class GuangMingDaily(Source):
    key = "gmw"
    name = "光明日报"
    priority = 85

    def list_articles(self, fetcher, date_str, rate):
        year, month, day = date_str.split("-")
        found = {}
        for page, channel in PAGES:
            html = fetcher.get_optional(page, rate=rate)
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                absolute = urljoin(page, a["href"].strip())
                m = DATE_RE.search(absolute)
                if not m or (m.group(1), m.group(2), m.group(3)) != (year, month, day):
                    continue
                title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
                if len(title) < 7:
                    continue
                found[absolute] = {"url": absolute, "title": title, "channel": channel}
        return list(found.values())
