# -*- coding: utf-8 -*-
"""带按域名限速与重试的 HTTP 抓取器。

设计要点：
- 每个域名独立锁 + 独立时间戳，多站可并行、单站严格串行
- 人民网 robots.txt 要求 Crawl-delay: 120，必须真实遵守
"""
import logging
import random
import threading
import time
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)


class RateLimiter(object):
    """按域名的令牌间隔限速器"""

    def __init__(self):
        self._last = {}
        self._locks = {}
        self._guard = threading.Lock()

    def _lock_for(self, host):
        with self._guard:
            lock = self._locks.get(host)
            if lock is None:
                lock = threading.Lock()
                self._locks[host] = lock
            return lock

    def wait(self, url, rate):
        host = urlparse(url).netloc
        lock = self._lock_for(host)
        with lock:
            elapsed = time.time() - self._last.get(host, 0)
            gap = rate - elapsed
            if gap > 0:
                time.sleep(gap + random.uniform(0, 0.6))
            self._last[host] = time.time()


class NotFound(Exception):
    """404 等确定性不存在，不重试"""


class Fetcher(object):
    def __init__(self, cfg):
        self.timeout = cfg.get("timeout", 25)
        self.retries = cfg.get("retries", 3)
        self.backoff = cfg.get("retry_backoff", 4)
        self.limiter = RateLimiter()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": cfg.get("user_agent", "Mozilla/5.0"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
        })
        self.stats = {"ok": 0, "fail": 0}
        self._cache = {}          # 列表页缓存：回看多日时避免重复请求

    def get(self, url, rate=5.0, encoding=None, use_cache=False):
        if use_cache and url in self._cache:
            return self._cache[url]
        text = self._get(url, rate, encoding)
        if use_cache:
            self._cache[url] = text
        return text

    def _get(self, url, rate=5.0, encoding=None):
        last_err = None
        for attempt in range(1, self.retries + 1):
            self.limiter.wait(url, rate)
            try:
                headers = {}
                parsed = urlparse(url)
                headers["Referer"] = "%s://%s/" % (parsed.scheme, parsed.netloc)
                resp = self.session.get(url, timeout=self.timeout,
                                        allow_redirects=True, headers=headers)
                if resp.status_code == 200:
                    if encoding:
                        resp.encoding = encoding
                    elif not resp.encoding or resp.encoding.lower() in ("iso-8859-1",):
                        resp.encoding = resp.apparent_encoding or "utf-8"
                    self.stats["ok"] += 1
                    return resp.text
                if resp.status_code in (404, 410):
                    self.stats["fail"] += 1
                    raise NotFound("HTTP %s %s" % (resp.status_code, url))
                last_err = RuntimeError("HTTP %s" % resp.status_code)
            except NotFound:
                raise
            except Exception as exc:  # noqa: BLE001
                last_err = exc
            if attempt < self.retries:
                wait = self.backoff ** attempt
                log.warning("抓取失败(%s/%s) %s -> %s，%.0fs 后重试",
                            attempt, self.retries, url, last_err, wait)
                time.sleep(wait)
        self.stats["fail"] += 1
        raise RuntimeError("抓取失败 %s: %s" % (url, last_err))

    def get_optional(self, url, rate=5.0, use_cache=True):
        try:
            return self.get(url, rate=rate, use_cache=use_cache)
        except Exception as exc:  # noqa: BLE001
            log.debug("跳过 %s: %s", url, exc)
            return None
