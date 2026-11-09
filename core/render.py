# -*- coding: utf-8 -*-
"""生成静态站：首页（近 N 天）/ 归档 / 每期页 / 单篇页。"""
import datetime
import os
import shutil

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.config import load_config, path
from core import store

WEEKDAY_CN = "一二三四五六日"


def date_cn(date_str):
    try:
        d = datetime.date.fromisoformat(date_str)
        return "%d年%d月%d日" % (d.year, d.month, d.day)
    except Exception:                      # noqa: BLE001
        return date_str


def weekday_cn(date_str):
    try:
        d = datetime.date.fromisoformat(date_str)
        return "周" + WEEKDAY_CN[d.weekday()]
    except Exception:                      # noqa: BLE001
        return ""


def short_date(date_str):
    """11月9日 —— 首页日期胶囊用短格式"""
    try:
        d = datetime.date.fromisoformat(date_str)
        return "%d/%d" % (d.month, d.day)
    except Exception:                      # noqa: BLE001
        return date_str


def _flow_nodes(analysis):
    """只展示真实存在的小标题；没有小标题结构时返回空，由模板显示占位"""
    st = analysis.get("structure", {})
    headers = st.get("headers") or []
    seen, nodes = set(), []
    for item in headers:
        item = (item or "").strip()
        key = item[:8]
        if not key or key in seen:
            continue
        seen.add(key)
        nodes.append(item[:10])
        if len(nodes) >= 3:
            break
    return nodes


def _tags(analysis):
    st = analysis.get("structure", {})
    tags = []
    if st.get("sectioned"):
        tags.append("小标题分层")
    if st.get("echo"):
        tags.append("首尾呼应")
    tags.extend(analysis.get("evidence_types") or [])
    return tags


def _blocks(article):
    paragraphs = [p for p in (article.get("body") or "").split("\n") if p.strip()]
    analysis = article.get("analysis") or {}
    headers = (analysis.get("structure") or {}).get("headers") or []
    total = len(paragraphs)
    out, point_idx = [], 0
    for i, para in enumerate(paragraphs):
        if i == 0:
            kind, label = "opening", "开篇立论"
        elif i == total - 1:
            kind, label = "closing", "结尾收束"
        elif para in headers:
            point_idx += 1
            kind, label = "header", "分论点 %d" % point_idx
        else:
            kind, label = "body", ""
        out.append({"text": para, "kind": kind, "label": label})
    return out


def build_site(picked_by_date=None, out_dir=None):
    """picked_by_date: {date: [article_id,...]}；不传则用库存全部达标文章"""
    cfg = load_config()
    site_cfg = cfg["site"]
    out_dir = out_dir or path(cfg["paths"]["site"])
    recent_n = int(site_cfg.get("recent_days", 10))

    env = Environment(
        loader=FileSystemLoader(path("templates")),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["date_cn"] = date_cn
    env.filters["short_date"] = short_date

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # 静态资源
    shutil.copy(path("static", "style.css"), os.path.join(out_dir, "style.css"))
    with open(os.path.join(out_dir, "_headers"), "w", encoding="utf-8") as fh:
        fh.write("/*\n  X-Robots-Tag: noindex, nofollow\n")
    # GitHub Pages / 静态托管：跳过 Jekyll，保住 _headers 这类下划线文件
    open(os.path.join(out_dir, ".nojekyll"), "w").close()

    # ---------- 第一阶段：整理每天的期次与文章 ----------
    dates = sorted(store.list_dates(), key=lambda x: x["date"])
    days = []
    for idx, row in enumerate(dates, 1):
        date_str = row["date"]
        if picked_by_date and date_str in picked_by_date:
            picked = [store.get_article(aid) for aid in picked_by_date[date_str]]
            picked = [a for a in picked if a]
        else:
            articles = store.list_by_date(date_str)
            picked = [a for a in articles
                      if a["analysis"].get("score", 0) >= cfg["score"]["review_score"]]
            picked = picked[: cfg["score"]["daily_count"]]
        if not picked:
            continue

        cards, art_pages = [], []
        for order, art in enumerate(picked, 1):
            analysis = art.get("analysis") or {}
            slug = "%s-%d" % (date_str.replace("-", ""), order)
            cards.append({
                "slug": slug,
                "title": art.get("title"),
                "source": art.get("source"),
                "channel": art.get("channel"),
                "score": analysis.get("score", 0),
                "claim": (analysis.get("structure") or {}).get("claim", ""),
                "flow_nodes": _flow_nodes(analysis),
                "tags": _tags(analysis),
                "char_count": analysis.get("char_count", 0),
            })
            art_pages.append({
                "art": {
                    "slug": slug,
                    "title": art.get("title"),
                    "source": art.get("source"),
                    "channel": art.get("channel"),
                    "url": art.get("url"),
                    "score": analysis.get("score", 0),
                    "char_count": analysis.get("char_count", 0),
                    "flow_nodes": _flow_nodes(analysis),
                },
                "blocks": _blocks(art),
                "site": site_cfg,
                "up": "../../",          # 相对根目录的层级：/a/{slug}/
            })

        days.append({
            "date": date_str,
            "date_cn": date_cn(date_str),
            "weekday": weekday_cn(date_str),
            "short": short_date(date_str),
            "seq": idx,
            "n": len(picked),
            "cards": cards,
            "art_pages": art_pages,
        })

    # 上一期（更早）/ 下一期（更新）
    for i, day in enumerate(days):
        day["prev"] = days[i - 1] if i > 0 else None
        day["next"] = days[i + 1] if i + 1 < len(days) else None

    # ---------- 第二阶段：渲染 ----------
    issue_tpl = env.get_template("issue.html")
    art_tpl = env.get_template("article.html")
    for day in days:
        for page in day["art_pages"]:
            art_dir = os.path.join(out_dir, "a", page["art"]["slug"])
            os.makedirs(art_dir, exist_ok=True)
            with open(os.path.join(art_dir, "index.html"), "w", encoding="utf-8") as fh:
                fh.write(art_tpl.render(**page))

        issue_dir = os.path.join(out_dir, "d", day["date"])
        os.makedirs(issue_dir, exist_ok=True)
        with open(os.path.join(issue_dir, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(issue_tpl.render(site=site_cfg, issue=day, articles=day["cards"], up="../../"))

    desc = list(reversed(days))
    recent = desc[:recent_n]
    older = desc[recent_n:]

    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(env.get_template("index.html").render(
            site=site_cfg, days=recent, total=len(desc),
            recent_n=recent_n, older_count=len(older), up=""))

    archive_dir = os.path.join(out_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    with open(os.path.join(archive_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(env.get_template("archive.html").render(site=site_cfg, days=desc, up="../"))

    return out_dir
