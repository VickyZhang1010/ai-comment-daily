# -*- coding: utf-8 -*-
"""采集源基类与注册表。每个站点一个模块，只负责产出候选链接。"""
import logging

log = logging.getLogger(__name__)

REGISTRY = {}


class Source(object):
    key = ""
    name = ""
    # 媒体权重：跨站判重时保留首发源
    priority = 50

    def list_articles(self, fetcher, date_str, rate):
        """返回 [{url, title, channel}]，只要目标日期的文章"""
        raise NotImplementedError

    def register(self):
        REGISTRY[self.key] = self
        return self


def register(cls):
    cls().register()
    return cls


def all_sources():
    import os
    import importlib
    pkg_dir = os.path.dirname(__file__)
    for fname in sorted(os.listdir(pkg_dir)):
        if fname.endswith(".py") and fname not in ("__init__.py", "base.py"):
            importlib.import_module("adapters." + fname[:-3])
    return REGISTRY
