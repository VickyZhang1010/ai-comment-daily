# -*- coding: utf-8 -*-
"""入口：采集 / 判分 / 生成 / 推送。

用法：
  python run.py test-push              发一条测试消息
  python run.py collect [--date D]     只跑采集，打印候选
  python run.py build   [--date D]     采集+判分+生成站点（不推送）
  python run.py daily   [--date D]     完整流程（含部署与推送）
"""
import argparse
import datetime
import hashlib
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters.base import all_sources          # noqa: E402
from core import store                          # noqa: E402
from core.config import load_config, load_env, path  # noqa: E402
from core.dedupe import dedupe                  # noqa: E402
from core.extract import extract                # noqa: E402
from core.fetcher import Fetcher                # noqa: E402
from core.pick import pick                      # noqa: E402
from core.render import build_site              # noqa: E402
from core.score import score_article            # noqa: E402

_log_handlers = [
    logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "logs", "run.log"), encoding="utf-8"),
]
# pythonw.exe（任务计划无控制台）下 sys.stdout 为 None
if sys.stdout is not None:
    _log_handlers.insert(0, logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=_log_handlers,
)
log = logging.getLogger("run")


def _wait_network(timeout=180):
    """开机后网络可能尚未就绪，先等连通再跑"""
    import socket
    import time
    start = time.time()
    while time.time() - start < timeout:
        try:
            socket.create_connection(("www.baidu.com", 443), timeout=5).close()
            return True
        except OSError:
            time.sleep(5)
    log.warning("网络在 %ds 内未就绪，继续尝试", timeout)
    return False


def target_date(offset_days=None):
    cfg = load_config()
    offset = cfg["collect"].get("lookback_days", 1) if offset_days is None else offset_days
    return (datetime.date.today() - datetime.timedelta(days=offset)).isoformat()


def collect_candidates(dates, limit_per_source=20, skip_slow=False):
    """dates 为日期列表（新→旧）。同一 URL 只保留一次。"""
    if isinstance(dates, str):
        dates = [dates]
    cfg = load_config()
    fetcher = Fetcher(cfg["collect"])
    sources = all_sources()

    items, seen = [], set()
    for key, src_cfg in cfg["sources"].items():
        if not src_cfg.get("enabled", True):
            continue
        rate = src_cfg.get("rate", 5)
        if skip_slow and rate >= 60:
            log.info("%-8s 跳过（慢速源 rate=%ss）", src_cfg.get("name", key), rate)
            continue
        src = sources.get(key)
        if src is None:
            log.warning("未找到采集源实现：%s", key)
            continue
        got = 0
        for day in dates:
            try:
                found = src.list_articles(fetcher, day, rate)
            except Exception as exc:                 # noqa: BLE001
                log.error("%s %s 列表抓取失败：%s", src.name, day, exc)
                continue
            for it in found:
                if it["url"] in seen:
                    continue
                seen.add(it["url"])
                it["source"] = src.name
                it["source_key"] = src.key
                it["priority"] = src.priority
                it["pub_date"] = day
                items.append(it)
                got += 1
                if got >= limit_per_source:
                    break
            if got >= limit_per_source:
                break
        log.info("%-8s 候选 %d 篇（限速 %ss）", src.name, got, rate)
    return items, fetcher


def cmd_collect(date_str):
    items, fetcher = collect_candidates(date_str)
    print("\n" + "=" * 70)
    print("共 %d 个候选链接 | 请求 ok=%d fail=%d" % (len(items), fetcher.stats["ok"], fetcher.stats["fail"]))
    for it in items:
        print("[%s] %s\n    %s" % (it["source"], it["title"], it["url"]))
    return items


def cmd_enrich(dates, save=True, skip_slow=False):
    """抓正文 + 打分。dates 为窗口日期列表（新→旧），越新的文章排序越靠前。"""
    if isinstance(dates, str):
        dates = [dates]
    base = dates[0]
    cfg = load_config()
    items, fetcher = collect_candidates(dates, skip_slow=skip_slow)
    scored = []
    per_source = {}
    for it in items:
        rate = cfg["sources"].get(it["source_key"], {}).get("rate", 5)
        # 慢速源（如人民网 Crawl-delay 120）严格限量，避免单站吃掉几十分钟
        cap = 4 if rate >= 60 else 20
        used_n = per_source.get(it["source_key"], 0)
        if used_n >= cap:
            continue
        per_source[it["source_key"]] = used_n + 1
        try:
            html = fetcher.get(it["url"], rate=rate)
        except Exception as exc:                     # noqa: BLE001
            log.warning("正文抓取失败 %s: %s", it["url"], exc)
            continue
        doc = extract(html, it["url"], expect_title=it["title"])
        if doc["char_count"] < 300:
            log.info("正文过短，跳过：[%s] %s (%d字)", it.get("source"),
                     (doc["title"] or it["title"])[:26], doc["char_count"])
            continue
        analysis = score_article(doc["title"] or it["title"], doc["paragraphs"],
                                 cfg["score"], channel=it.get("channel", ""))
        record = dict(it)
        record.update({
            "id": hashlib.sha1(it["url"].encode("utf-8")).hexdigest()[:16],
            "title": doc["title"] or it["title"],
            "paragraphs": doc["paragraphs"],
            "body": "\n".join(doc["paragraphs"]),
            "char_count": doc["char_count"],
            "analysis": analysis,
        })
        scored.append(record)
        log.info("得分 %3d | %s", analysis["score"], record["title"][:36])

    def rank(rec):
        gap = 0
        try:
            gap = (datetime.date.fromisoformat(base)
                   - datetime.date.fromisoformat(rec.get("pub_date") or base)).days
        except Exception:                            # noqa: BLE001
            pass
        return -(rec["analysis"]["score"] - gap * 4)  # 每晚一天扣 4 分

    scored.sort(key=rank)
    return scored, fetcher


def cmd_test_push():
    from core.push import send_markdown
    ok = send_markdown("**官媒议论文日报 · 连通性测试**\n\n推送通道正常。")
    print("推送结果：", ok)


def _window(end_date, days):
    base = datetime.date.fromisoformat(end_date)
    return [(base - datetime.timedelta(days=i)).isoformat() for i in range(days)]


def cmd_build(date_str, skip_slow=False):
    cfg = load_config()
    window = cfg["collect"].get("window_days", 3)
    dates = _window(date_str, window)
    log.info("采集窗口：%s", " / ".join(dates))
    scored, fetcher = cmd_enrich(dates, skip_slow=skip_slow)
    if not scored:
        log.warning("没有可用候选，未生成内容")
        return []

    before = len(scored)
    scored = dedupe(scored)
    if before != len(scored):
        log.info("跨站判重：%d → %d 篇", before, len(scored))

    # 判重按媒体优先级排序，这里恢复为「结构度 + 时效」排序
    def _rank(rec):
        gap = 0
        try:
            gap = (datetime.date.fromisoformat(date_str)
                   - datetime.date.fromisoformat(rec.get("pub_date") or date_str)).days
        except Exception:                            # noqa: BLE001
            pass
        return -(rec["analysis"]["score"] - gap * 4)

    scored.sort(key=_rank)

    store.save_articles(scored, date_str)
    picked = pick(scored, cfg["score"])
    store.save_edition(date_str, "built", [r["id"] for r in picked])

    log.info("=" * 60)
    log.info("入选 %d 篇：", len(picked))
    for idx, rec in enumerate(picked, 1):
        log.info("  %d. [%d分] %s —— %s（%s）", idx, rec["analysis"]["score"],
                 rec["title"][:32], rec["source"], rec.get("pub_date", ""))
    out = build_site({date_str: [r["id"] for r in picked]})
    log.info("站点已生成：%s", out)
    publish_site()
    return picked


def publish_site():
    """把 docs/ 推到 GitHub，触发 Pages 重新发布。

    本机到 github.com 的 Git 协议被拦，故走 api.github.com 的 Git Data API。
    未配置 GITHUB_TOKEN 时静默跳过，不影响本地构建与微信推送。
    """
    if not os.environ.get("GITHUB_TOKEN", "").strip():
        log.info("未配置 GITHUB_TOKEN，跳过 GitHub 发布")
        return False
    try:
        import push_api
        push_api.main()
        log.info("GitHub 已更新：%s", _site_base() or "")
        return True
    except SystemExit as exc:
        log.error("GitHub 发布失败：%s", exc)
    except Exception as exc:                       # noqa: BLE001
        log.error("GitHub 发布异常：%s", exc)
    return False


def cmd_rebuild(date_str):
    """不重新抓取，直接用库中已有文章重新选题与渲染"""
    cfg = load_config()
    rows = store.list_by_date(date_str)
    if not rows:
        log.error("库中没有 %s 的文章，请先运行 build", date_str)
        return []
    picked = pick(rows, cfg["score"])
    store.save_edition(date_str, "built", [r["id"] for r in picked])
    log.info("入选 %d 篇：", len(picked))
    for idx, rec in enumerate(picked, 1):
        log.info("  %d. [%d分] %s —— %s", idx, rec["analysis"]["score"],
                 rec["title"][:34], rec["source"])
    out = build_site({date_str: [r["id"] for r in picked]})
    log.info("重建完成：%s", out)
    return picked


def _picked_from_db(date_str):
    import json
    ed = store.get_edition(date_str)
    if not ed:
        return []
    ids = json.loads(ed.get("picked") or "[]")
    return [a for a in (store.get_article(i) for i in ids) if a]


def _pushed(date_str):
    ed = store.get_edition(date_str)
    return bool(ed and ed["status"] == "pushed")


def _site_base():
    cfg = load_config()
    return (os.environ.get("SITE_BASE_URL") or cfg["site"].get("base_url") or "").rstrip("/")


def _share_code():
    cfg = load_config()
    return (os.environ.get("SITE_SHARE_CODE") or cfg["site"].get("share_code") or "").strip()


def _with_code(url):
    code = _share_code()
    if not code:
        return url
    sep = "&" if "?" in url else "?"
    return "%s%ssharecode=%s" % (url, sep, code)


def _site_url(date_str):
    base = _site_base()
    if not base:
        return ""
    return _with_code(base + "/d/%s/" % date_str)


def _home_url():
    base = _site_base()
    return _with_code(base + "/") if base else ""


def _url_ok(url, timeout=6):
    """推送前探活，避免把死链发给用户"""
    try:
        import requests
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        return resp.status_code == 200
    except Exception:                            # noqa: BLE001
        return False


def _do_push(date_str, picked):
    from core.push import push_digest
    if not picked:
        return False
    issue_url = _site_url(date_str)
    home = _home_url()
    if issue_url and not _url_ok(issue_url):
        log.warning("线上当期页不可访问（%s），本次只推归档首页", issue_url)
        issue_url = ""
    if not issue_url and not home:
        log.warning("未配置站点地址，本次推送不含链接")
    ok = push_digest(date_str, picked, issue_url, home)
    if ok:
        store.mark_pushed(date_str)
        log.info("推送成功：%s（%d 篇，链接 %s）", date_str, len(picked),
                 issue_url or home or "无")
    else:
        log.error("推送失败：%s", date_str)
    return ok


def _save_base_url(url):
    """把部署地址写回 config.yaml，供推送拼链接"""
    cfg_path = path("config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        if re.search(r"^\s*base_url:", text, re.M):
            text = re.sub(r"^\s*base_url:.*$", '  base_url: "%s"' % url,
                          text, count=1, flags=re.M)
        else:
            text = text.replace("site:\n", 'site:\n  base_url: "%s"\n' % url, 1)
        with open(cfg_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except Exception as exc:                    # noqa: BLE001
        log.warning("写回 base_url 失败：%s", exc)


def _deploy_site():
    try:
        from deploy import deploy
        url = deploy(verbose=True)
        if url:
            os.environ["SITE_BASE_URL"] = url
            _save_base_url(url)
            log.info("站点已部署：%s", url)
        return url
    except Exception as exc:                    # noqa: BLE001
        log.warning("部署失败（不影响本地生成）：%s", exc)
        return None


def cmd_morning_build(date_str):
    """08:30 采集+判分+渲染+部署，为 09:00 推送备好内容"""
    if _pushed(date_str):
        log.info("%s 已推送过，跳过采集", date_str)
        return []
    picked = cmd_build(date_str)
    if picked:
        _deploy_site()
    return picked


def cmd_morning_push(date_str):
    """09:00 只负责推送已生成的内容"""
    if _pushed(date_str):
        log.info("%s 已推送过，跳过", date_str)
        return
    picked = _picked_from_db(date_str)
    if not picked:
        log.warning("%s 没有已生成的期次，现场构建", date_str)
        picked = cmd_build(date_str)
    _do_push(date_str, picked)


def cmd_catchup(date_str):
    """开机/登录补推：未推送则立即完整走一遍"""
    if _pushed(date_str):
        log.info("%s 已推送过，无需补推", date_str)
        return
    _wait_network()
    log.info("未推送，开始补推 %s", date_str)
    picked = cmd_build(date_str)
    if picked:
        _deploy_site()
    _do_push(date_str, picked)


def main():
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("command",
                        choices=["test-push", "collect", "enrich", "build", "rebuild", "daily",
                                 "morning-build", "morning-push", "catchup"])
    parser.add_argument("--date", default=None)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--skip-slow", action="store_true",
                        help="跳过 rate>=60 的慢速源（快速调试用）")
    args = parser.parse_args()

    if args.command == "test-push":
        cmd_test_push()
        return

    date_str = args.date or target_date()
    log.info("目标日期：%s", date_str)

    if args.command == "collect":
        cmd_collect(date_str)
    elif args.command == "enrich":
        scored, _ = cmd_enrich(date_str)
        print("\n" + "=" * 70)
        for r in scored[:15]:
            a = r["analysis"]
            print("%3d %s [%s] %d字 段落%d %s" % (
                a["score"], r["title"][:38], r["source"], a["char_count"],
                a["paragraph_count"], a["reason"]))
    elif args.command == "build":
        cmd_build(date_str, skip_slow=args.skip_slow)
    elif args.command == "rebuild":
        cmd_rebuild(date_str)
    elif args.command == "daily":
        cmd_catchup(date_str)
    elif args.command == "morning-build":
        cmd_morning_build(date_str)
    elif args.command == "morning-push":
        cmd_morning_push(date_str)
    elif args.command == "catchup":
        cmd_catchup(target_date())
    else:
        print("该命令尚未实现")


if __name__ == "__main__":
    main()
