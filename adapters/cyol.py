# -*- coding: utf-8 -*-
"""中国青年报电子版：静态 HTML，结构最规整。

版面数量随星期变化（周日通常只有 4 版），因此不硬编码版面号：
先取 01 版解析"版面目录"，再只抓含评论/理论/要闻的版面。
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from adapters.base import Source, register

TEMPLATE = "https://zqb.cyol.com/pc/layout/{ym}/{dd}/node_{page}.html"
ARTICLE_RE = re.compile(r"/content/\d{6}/\d{2}/content_\d+\.html$")
PAGE_RE = re.compile(r"node_(\d{2})\.html")
LABEL_RE = re.compile(r"(\d{2})\s*版\s*[：:]\s*(.+)")
WANTED = ("评论", "理论", "要闻", "思想", "青年话题", "观点")


@register
class ChinaYouthDaily(Source):
    key = "cyol"
    name = "中国青年报"
    priority = 70

    def _layouts(self, fetcher, ym, dd, rate):
        html = fetcher.get_optional(TEMPLATE.format(ym=ym, dd=dd, page="01"), rate=rate)
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        pages = {}
        for a in soup.find_all("a", href=True):
            m = PAGE_RE.search(a["href"])
            if not m:
                continue
            label = LABEL_RE.search(a.get_text(" ", strip=True))
            if label:
                pages[m.group(1)] = label.group(2).strip()
        return sorted(pages.items())

    def list_articles(self, fetcher, date_str, rate):
        year, month, day = date_str.split("-")
        ym = year + month
        layouts = self._layouts(fetcher, ym, day, rate)
        if not layouts:
            return []

        targets = [(num, name) for num, name in layouts
                   if any(k in name for k in WANTED)] or layouts

        found = {}
        for num, name in targets:
            page_url = TEMPLATE.format(ym=ym, dd=day, page=num)
            html = fetcher.get_optional(page_url, rate=rate)
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                absolute = urljoin(page_url, a["href"].strip())
                if not ARTICLE_RE.search(absolute):
                    continue
                title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
                if len(title) < 6:
                    continue
                found[absolute] = {"url": absolute, "title": title,
                                   "channel": "第%s版 %s" % (num, name)}
        return list(found.values())
