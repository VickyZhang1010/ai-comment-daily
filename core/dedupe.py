# -*- coding: utf-8 -*-
"""跨站判重：同一篇评论常被多家转载（人民日报 → 人民网 → 求是网…）。"""
import hashlib
import re


def _hash64(text):
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:16], 16)


def _tokens(text):
    clean = re.sub(r"[^\u4e00-\u9fa5]", "", text)
    return [clean[i:i + 2] for i in range(len(clean) - 1)]


def simhash(text):
    vec = [0] * 64
    for tok in _tokens(text):
        h = _hash64(tok)
        for i in range(64):
            vec[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(64):
        if vec[i] > 0:
            out |= 1 << i
    return out


def hamming(a, b):
    return bin(a ^ b).count("1")


def dedupe(records, threshold=6):
    """records 需含 title / body / priority；保留首发源（priority 高者）"""
    kept = []
    for rec in sorted(records, key=lambda r: -r.get("priority", 50)):
        fp_title = simhash(rec.get("title", ""))
        fp_body = simhash((rec.get("body") or "")[:1200])
        duplicate = False
        for exist in kept:
            if (hamming(fp_title, exist["_fp_title"]) <= 3
                    and hamming(fp_body, exist["_fp_body"]) <= threshold):
                duplicate = True
                break
        if not duplicate:
            rec["_fp_title"] = fp_title
            rec["_fp_body"] = fp_body
            kept.append(rec)
    return kept
