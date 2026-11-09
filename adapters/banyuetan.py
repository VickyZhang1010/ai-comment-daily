# -*- coding: utf-8 -*-
"""半月谈评论：静态 HTML。

列表 http://www.banyuetan.org/byt/banyuetanpinglun/index.html
文章 http://www.banyuetan.org/pl/detail/20261109/xxxx_1.html
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from adapters.base import Source, register

PAGES = [
    ("http://www.banyuetan.org/byt/banyuetanpinglun/index.html", "半月谈评论"),
]
DATE_RE = re.compile(r"/detail/(20\d{6})/")


@register
class BanYueTan(Source):
    key = "banyuetan"
    name = "半月谈"
    priority = 75

    def list_articles(self, fetcher, date_str, rate):
        target = date_str.replace("-", "")
        found = {}
        for page, channel in PAGES:
            html = fetcher.get_optional(page, rate=rate)
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                absolute = urljoin(page, a["href"].strip())
                m = DATE_RE.search(absolute)
                if not m or m.group(1) != target:
                    continue
                title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
                if len(title) < 7:
                    continue
                found[absolute] = {"url": absolute, "title": title, "channel": channel}
        return list(found.values())
