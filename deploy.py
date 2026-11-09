# -*- coding: utf-8 -*-
"""部署到 Cloudflare Pages（Direct Upload，走 wrangler，不需要 Git 仓库）。

前置：在 .env 里配置 CF_API_TOKEN 与 CF_ACCOUNT_ID。
Token 权限：Account → Cloudflare Pages → Edit。
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import ROOT, load_env


def deploy(verbose=True):
    load_env()
    token = (os.environ.get("CF_API_TOKEN") or "").strip()
    account = (os.environ.get("CF_ACCOUNT_ID") or "").strip()
    project = (os.environ.get("CF_PROJECT_NAME") or "ai-comment-daily").strip()

    if not token or not account:
        print("跳过部署：未配置 CF_API_TOKEN / CF_ACCOUNT_ID")
        return None

    env = dict(os.environ)
    env["CLOUDFLARE_API_TOKEN"] = token
    env["CLOUDFLARE_ACCOUNT_ID"] = account
    env["CI"] = "1"                          # 关闭交互式提示
    env["WRANGLER_SEND_METRICS"] = "false"

    site_dir = os.path.join(ROOT, "docs")

    # 首次部署时项目还不存在，wrangler 会直接报 Project not found，
    # 所以先尝试创建（已存在会失败，忽略即可）
    create_cmd = ('npx --yes wrangler@latest pages project create %s '
                  '--production-branch main' % project)
    create = subprocess.run(
        create_cmd, shell=True, cwd=ROOT, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if verbose:
        print("[wrangler] %s" % ("已创建 Pages 项目"
                                 if create.returncode == 0 else "项目已存在，继续部署"))

    cmd = ('npx --yes wrangler@latest pages deploy "%s" '
           '--project-name %s --branch main --commit-dirty=true' % (site_dir, project))

    proc = subprocess.run(
        cmd, shell=True, cwd=ROOT, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    if verbose:
        print(output[-2500:])

    # wrangler 输出里同时有 "<hash>.<project>.pages.dev"（每次部署都变）和
    # 固定的 "<project>.pages.dev"，必须优先取后者，否则每天链接都会漂移
    prod = re.search(r"https://%s\.pages\.dev" % re.escape(project), output)
    if proc.returncode == 0 and prod:
        return prod.group(0)
    match = re.search(r"https://[a-z0-9-]+\.pages\.dev", output)
    if proc.returncode == 0 and match:
        return match.group(0)
    return None


if __name__ == "__main__":
    url = deploy()
    print("部署结果：", url or "失败")
