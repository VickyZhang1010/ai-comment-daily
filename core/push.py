# -*- coding: utf-8 -*-
"""企业微信群机器人推送。

限制（官方）：
- 每个机器人每分钟最多 20 条
- markdown content 上限 4096 字节（UTF-8，中文约 3 字节/字）
"""
import json
import logging
import os
import time

import requests

log = logging.getLogger(__name__)

MAX_BYTES = 4000          # 留出安全余量


def _webhook():
    url = os.environ.get("WECOM_WEBHOOK", "").strip()
    if not url:
        raise RuntimeError("未配置 WECOM_WEBHOOK")
    return url


def _byte_len(text):
    return len(text.encode("utf-8"))


def split_content(content, limit=MAX_BYTES):
    """按段落切分超长 markdown，保持语义完整"""
    if _byte_len(content) <= limit:
        return [content]
    chunks, buf = [], ""
    for para in content.split("\n\n"):
        candidate = (buf + "\n\n" + para) if buf else para
        if _byte_len(candidate) > limit and buf:
            chunks.append(buf)
            buf = para
        else:
            buf = candidate
    if buf:
        chunks.append(buf)
    return chunks


def send_markdown(content, retries=2):
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    return _post(payload, retries=retries)


def send_text(content, retries=2):
    payload = {"msgtype": "text", "text": {"content": content}}
    return _post(payload, retries=retries)


def _post(payload, retries=2):
    url = _webhook()
    for attempt in range(1, retries + 2):
        try:
            resp = requests.post(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            data = resp.json()
            if data.get("errcode") == 0:
                return True
            log.error("推送返回错误：%s", data)
            if data.get("errcode") == 45009:      # 频率超限
                time.sleep(20)
                continue
            return False
        except Exception as exc:                  # noqa: BLE001
            log.warning("推送异常(%s/%s)：%s", attempt, retries + 1, exc)
            time.sleep(3 * attempt)
    return False


def push_digest(date_str, picked, site_url, home_url=""):
    """一条目录消息：今日 N 篇 + 站点链接"""
    lines = ["**官媒议论文日报 · %s**" % _cn_date(date_str), ""]
    lines.append("本期 %d 篇（均为「总—分—总」结构）" % len(picked))
    lines.append("")
    for idx, art in enumerate(picked, 1):
        a = art["analysis"]
        lines.append("**%d. %s**" % (idx, art["title"]))
        lines.append("<font color=\"comment\">%s · %s</font>" % (art["source"], art.get("channel", "")))
        claim = (a["structure"].get("claim") or "")[:42]
        if claim:
            lines.append("　论点：%s" % claim)
        lines.append("")
    if site_url:
        lines.append("> 结构拆解（立论 / 分论点 / 收束）：[点此阅读本期](%s)" % site_url)
    elif home_url:
        lines.append("> 本期页面待同步，站内可先看往期归档")
    if home_url:
        lines.append("> 往期归档：[全部期次](%s)" % home_url)
    return send_markdown("\n".join(lines))


def _cn_date(date_str):
    try:
        y, m, d = date_str.split("-")
        return "%d月%d日" % (int(m), int(d))
    except Exception:                             # noqa: BLE001
        return date_str
