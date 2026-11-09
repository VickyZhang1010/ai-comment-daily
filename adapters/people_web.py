# -*- coding: utf-8 -*-
"""人民网观点频道。

注意：people.com.cn 的 robots.txt 声明 Crawl-delay: 120，
本适配器严格依赖 config 里该源的 rate=120，请勿调低。
文章 URL 形如 http://opinion.people.com.cn/n1/2026/1109/c461529-40830087.html
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from adapters.base import Source, register

PAGES = [
    ("http://opinion.people.com.cn/GB/223228/index.html", "人民网评论"),
]
DATE_RE = re.compile(r"/n1/(\d{4})/(\d{2})(\d{2})/c\d+-\d+\.html$")


@register
class PeopleWeb(Source):
    key = "people_web"
    name = "人民网"
    priority = 90

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
