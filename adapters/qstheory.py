# -*- coding: utf-8 -*-
"""求是网：求是网评 / 社论评论。

列表页上的文章链接形如 20261108/<32位hash>/c.html，日期直接可解析，
非常适合按日期筛选，无需翻页。
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from adapters.base import Source, register

PAGES = [
    ("https://www.qstheory.cn/qswp.htm", "求是网评"),
    ("https://www.qstheory.cn/v9zhuanqu/zhuanqu/slpl/index.htm", "社论评论"),
]

LINK_RE = re.compile(r"^(?:https?://[^/]+)?/(\d{8})/[0-9a-f]{32}/c\.html$")


@register
class QsTheory(Source):
    key = "qstheory"
    name = "求是网"
    priority = 80

    def list_articles(self, fetcher, date_str, rate):
        target = date_str.replace("-", "")
        found = {}
        for page, channel in PAGES:
            html = fetcher.get_optional(page, rate=rate)
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                absolute = urljoin(page, href)
                m = LINK_RE.match(absolute)
                if not m or m.group(1) != target:
                    continue
                title = a.get_text(" ", strip=True) or a.get("title", "")
                title = re.sub(r"\s+", " ", title).strip()
                if len(title) < 6:
                    continue
                found[absolute] = {"url": absolute, "title": title, "channel": channel}
        return list(found.values())
