# -*- coding: utf-8 -*-
"""正文抽取：基于段落密度的通用算法。

官媒站点结构差异很大，但共同点是正文由多个 <p> 构成。
这里不逐站维护 CSS 选择器，而是找出"<p> 总字数最多、嵌套最深"的容器，
再过滤导航、责任编辑、图片说明等噪声。
"""
import re

from bs4 import BeautifulSoup

# 注意：不能删 form —— 部分 ASP.NET 站点（如经济日报）整页包在 <form> 内
DROP_TAGS = ("script", "style", "noscript", "iframe", "svg", "button")

NOISE_PATTERNS = (
    r"^责任编辑[：:]", r"^编辑[：:]", r"^来源[：:]", r"^作者[：:]",
    r"^【?纠错】?$", r"^扫一扫", r"^阅读全文$", r"^返回顶部$", r"^分享到",
    r"^（?作者(单位|系)", r"^原标题[：:]", r"^点击进入", r"^上一篇", r"^下一篇",
    r"^相关阅读", r"^免责声明", r"^版权", r"^\[责任编辑", r"^（责任编辑",
    r"^\d{4}年\d{2}月\d{2}日", r"^第\d{2}版", r"^人民日报\s*\(", r"^新华社",
    r"^文章关键词", r"^关键词[：:]", r"^【打印】", r"^【关闭】",
    r"^新华社[^。]{0,12}电$", r"^本报[^。]{0,12}电$", r"^本报讯",
    r"^□", r"^本报记者", r"^文/图", r"^图/文", r"^（完）", r"^【字号",
)
NOISE_RE = re.compile("|".join(NOISE_PATTERNS))


def _flat(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def _depth(el):
    return len(list(el.parents))


def _is_noise(text):
    if len(text) < 12:
        return True
    if NOISE_RE.search(text):
        return True
    if text.count("|") >= 3:          # 导航条
        return True
    if text.startswith("http"):
        return True
    return False


# 官媒多用 TRS / 方正采编系统，正文容器命名高度一致
KNOWN_CONTAINER = re.compile(
    r"articleText|articleContent|article_content|article-content|articleBody"
    r"|trs_editor|TRS_UEDITOR|zoom|detail[-_]?content|content[-_]?text|main[-_]?text",
    re.I,
)


def _best_container(soup):
    """选正文容器：先认官媒常见的正文 id/class，再退回段落密度法"""
    candidates = []
    for el in soup.find_all(["div", "article", "section"]):
        key = " ".join(el.get("class") or []) + " " + (el.get("id") or "")
        if not KNOWN_CONTAINER.search(key):
            continue
        ps = el.find_all("p")
        if len(ps) < 2:
            continue
        total = sum(len(_flat(p)) for p in ps)
        if total < 200:
            continue
        candidates.append((_depth(el), total, el))
    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1]))
        return candidates[-1][2]

    best, best_key = None, (-1, 0)
    for el in soup.find_all(["div", "article", "section", "td"]):
        ps = el.find_all("p", recursive=False)
        if len(ps) < 2:
            continue
        total = sum(len(_flat(p)) for p in ps)
        if total < 200:
            continue
        link_chars = sum(len(_flat(a)) for a in el.find_all("a"))
        key = (total - link_chars, _depth(el))
        if key > best_key:
            best, best_key = el, key
    return best


def _meta(soup, names):
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return _flat(tag).strip()
    return ""


def _line_fallback(soup):
    """兜底：某些电子报整页只有 1 个 <p>，正文用 <br> 分行。

    把 <br> 转成换行后按行切分；用"纯文本量 - 链接文本量"排序，
    避免选中满是文章标题的版面导航块，并对 class/id 含 content/view 的容器加权。
    """
    for br in soup.find_all("br"):
        br.replace_with("\n")
    best_score, best_lines = -1, []
    for el in soup.find_all(["div", "td", "article", "section"]):
        raw = el.get_text("\n", strip=True)
        lines = []
        for line in raw.split("\n"):
            line = re.sub(r"\s+", " ", line).strip()
            if not _is_noise(line):
                lines.append(line)
        total = sum(len(x) for x in lines)
        if total < 200:
            continue
        link_chars = sum(len(re.sub(r"\s+", "", a.get_text())) for a in el.find_all("a"))
        pure = total - link_chars
        key = " ".join(el.get("class") or []) + " " + (el.get("id") or "")
        bonus = 300 if re.search(r"content|article|text|view|zoom|detail|body", key, re.I) else 0
        score_value = pure + bonus
        if score_value > best_score:
            best_score, best_lines = score_value, lines
    return best_lines


def _norm(text):
    return re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", text or "")


def _similar(a, b):
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    ga = set(na[i:i + 2] for i in range(len(na) - 1))
    gb = set(nb[i:i + 2] for i in range(len(nb) - 1))
    if not ga or not gb:
        return False
    return len(ga & gb) / float(min(len(ga), len(gb))) >= 0.6


def _clip_by_title(paragraphs, expect_title):
    """整版聚合页（如法治日报电子版）会把同版多篇文章拼在一起，
    从匹配到的标题处截取，累积足够正文后遇到"下一个文章标题"才停。
    匹配失败返回 None。
    """
    for idx, para in enumerate(paragraphs):
        if not _similar(para, expect_title):
            continue
        out = []
        for nxt in paragraphs[idx + 1:]:
            looks_like_title = (
                len(nxt) <= 30
                and not nxt.endswith(("。", "！", "？", "…", "”"))
                and not re.search(r"[，、；：]", nxt)
            )
            # 至少累积 200 字才允许在下一个标题处断开，避免把正文切空
            if looks_like_title and sum(len(x) for x in out) > 200:
                break
            out.append(nxt)
        if sum(len(x) for x in out) < 150:
            return None                # 截取失败
        return out
    return None


def extract(html, url="", expect_title=""):
    """返回 {title, paragraphs, char_count, publish_date}"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(DROP_TAGS):
        tag.decompose()

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = _flat(h1)
    if not title:
        title = _meta(soup, ("og:title", "twitter:title"))
    if not title and soup.title:
        title = re.split(r"[|_\-—]", _flat(soup.title))[0].strip()

    container = _best_container(soup)
    paras = []
    if container is not None:
        for p in container.find_all("p"):
            text = _flat(p)
            if not _is_noise(text):
                paras.append(text)
    if not paras:                      # 兜底：全文按段落切
        for p in soup.find_all("p"):
            text = _flat(p)
            if not _is_noise(text):
                paras.append(text)

    # 去重相邻重复段（有些站点正文与摘要重复）
    deduped = []
    for p in paras:
        if deduped and (p == deduped[-1] or p in deduped[-2:]):
            continue
        deduped.append(p)

    # 兜底：段落太少或字数不足时，改用按行切分
    if sum(len(x) for x in deduped) < 400 or len(deduped) < 3:
        fallback = _line_fallback(soup)
        if sum(len(x) for x in fallback) > sum(len(x) for x in deduped):
            deduped = fallback

    # 整版聚合页：按标题截取目标文章（列表页标题匹配失败时，改用页面自身标题）
    if expect_title:
        clipped = _clip_by_title(deduped, expect_title)
        if clipped is None and title:
            clipped = _clip_by_title(deduped, title)
        if clipped:
            deduped = clipped
        if deduped and _similar(deduped[0], expect_title):
            deduped = deduped[1:] or deduped

    # 最末级兜底：仍为空时，直接按行切分整页文本
    if not deduped:
        raw = soup.get_text("\n", strip=True)
        lines = [re.sub(r"\s+", " ", x).strip() for x in raw.split("\n")]
        deduped = [x for x in lines if len(x) >= 20 and not _is_noise(x)][:80]

    body = "\n".join(deduped)
    date = ""
    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", url)
    if m:
        date = "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))

    return {
        "title": title,
        "paragraphs": deduped,
        "char_count": len(body.replace("\n", "")),
        "publish_date": date,
        "author": _meta(soup, ("author", "og:article:author")),
    }
