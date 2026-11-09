# -*- coding: utf-8 -*-
"""选题：分数排序 + 同源上限 + 不足时放宽补位。"""


def _select(pool, limit, max_per_source, exclude_ids, counter):
    """counter 由调用方共享，确保"同源上限"跨轮次一致生效"""
    out = []
    for rec in pool:
        if len(out) >= limit:
            break
        if rec["id"] in exclude_ids:
            continue
        src = rec.get("source") or ""
        if counter.get(src, 0) >= max_per_source:
            continue
        out.append(rec)
        counter[src] = counter.get(src, 0) + 1
        exclude_ids.add(rec["id"])
    return out


def pick(records, cfg):
    """records 已按"结构度 + 时效"降序。返回入选文章列表。"""
    daily = cfg.get("daily_count", 5)
    min_score = cfg.get("min_score", 70)
    review = cfg.get("review_score", 60)
    max_src = cfg.get("max_per_source", 2)

    strong = [r for r in records if r["analysis"]["score"] >= min_score]
    weak = [r for r in records if review <= r["analysis"]["score"] < min_score]

    used = set()
    counter = {}
    picked = _select(strong, daily, max_src, used, counter)

    # 达标不足时用复核线文章补位（页面与推送会显示结构度，读者自行判断）
    if len(picked) < daily:
        picked += _select(weak, daily - len(picked), max_src, used, counter)

    return picked[:daily]
