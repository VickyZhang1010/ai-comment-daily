# -*- coding: utf-8 -*-
"""经济日报（中国经济网评论频道）：静态 HTML。

列表 http://views.ce.cn/
文章 http://views.ce.cn/view/ent/202611/t20261109_3287805.shtml
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from adapters.base import Source, register

PAGES = [
    ("http://views.ce.cn/", "经济日报评论"),
]
DATE_RE = re.compile(r"/t(20\d{6})\d*_\d+\.shtml")


@register
class ChinaEconomicNet(Source):
    key = "ce"
    name = "经济日报"
    priority = 85

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
