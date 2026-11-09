# -*- coding: utf-8 -*-
"""法治日报：走电子版（纯静态），绕开官网正文页的 JS 反爬挑战。

版面页 http://epaper.legaldaily.com.cn/fzrb/content/YYYYMMDD/Page{NN}TB.htm
文章页 http://epaper.legaldaily.com.cn/fzrb/content/YYYYMMDD/Articel{NN}{SEQ}GN.htm

评论文章主要分布在 02 法治 / 03 政法 / 07 综合，正文含"本报评论员"署名，
因此全量抓这几版，交给打分器筛选。
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from adapters.base import Source, register

BASE = "http://epaper.legaldaily.com.cn/fzrb/content/{ymd}/Page{page}TB.htm"
PAGES = [("02", "法治"), ("03", "政法"), ("07", "综合")]
ARTICLE_RE = re.compile(r"/Articel(\d{2})\d{3}GN\.htm$", re.I)


@register
class LegalDaily(Source):
    key = "legaldaily"
    name = "法治日报"
    priority = 60

    def list_articles(self, fetcher, date_str, rate):
        ymd = date_str.replace("-", "")
        found = {}
        for page_no, channel in PAGES:
            page_url = BASE.format(ymd=ymd, page=page_no)
            html = fetcher.get_optional(page_url, rate=rate)
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                absolute = urljoin(page_url, a["href"].strip())
                m = ARTICLE_RE.search(absolute)
                if not m or m.group(1) != page_no:
                    continue
                title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
                if len(title) < 7:
                    continue
                found[absolute] = {"url": absolute, "title": title,
                                   "channel": "第%s版 %s" % (page_no, channel)}
        return list(found.values())
