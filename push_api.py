"""通过 GitHub REST API 提交并推送（绕开 git 协议的 443 连通问题）。

本机到 github.com 的 HTTPS 会被拦，但 api.github.com 可用，
因此用 Git Data API（blobs → tree → commit → ref）完成推送。
"""
import base64
import os
import subprocess
import sys

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core.config import load_env  # noqa: E402

API = "https://api.github.com"


def main():
    load_env()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "").strip()
    if not token or "/" not in repo:
        raise SystemExit("缺少 GITHUB_TOKEN 或 GITHUB_REPO")
    owner, name = repo.split("/", 1)

    s = requests.Session()
    s.headers.update({
        "Authorization": "token " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-comment-daily-publisher",
    })

    # 用本地 git 索引确定要提交的文件（.gitignore 已生效）
    subprocess.run(["git", "add", "-A"], cwd=ROOT,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, stdout=subprocess.PIPE)
    paths = [p for p in out.stdout.decode("utf-8", "replace").splitlines() if p.strip()]
    print("待提交文件：%d 个" % len(paths))

    blobs = []
    for rel in paths:
        fp = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(fp):
            print("  跳过（不存在）：%s" % rel)
            continue
        data = base64.b64encode(open(fp, "rb").read()).decode("ascii")
        r = s.post(API + "/repos/%s/%s/git/blobs" % (owner, name),
                   json={"content": data, "encoding": "base64"}, timeout=60)
        if r.status_code not in (200, 201):
            raise SystemExit("建 blob 失败 %s: %s" % (rel, r.text[:200]))
        blobs.append({"path": rel, "mode": "100644", "type": "blob",
                      "sha": r.json()["sha"]})
    print("blob 上传完成：%d 个" % len(blobs))

    r = s.post(API + "/repos/%s/%s/git/trees" % (owner, name),
               json={"tree": blobs}, timeout=90)
    if r.status_code not in (200, 201):
        raise SystemExit("建 tree 失败：" + r.text[:300])
    tree_sha = r.json()["sha"]
    print("tree:", tree_sha)

    # 已有 main 则作为父提交
    parent = None
    r = s.get(API + "/repos/%s/%s/git/ref/heads/main" % (owner, name), timeout=30)
    if r.status_code == 200:
        parent = r.json()["object"]["sha"]
        print("父提交:", parent)

    payload = {"message": "通过 API 发布站点", "tree": tree_sha}
    if parent:
        payload["parents"] = [parent]
    r = s.post(API + "/repos/%s/%s/git/commits" % (owner, name), json=payload, timeout=60)
    if r.status_code not in (200, 201):
        raise SystemExit("建 commit 失败：" + r.text[:300])
    commit_sha = r.json()["sha"]
    print("commit:", commit_sha)

    if parent:
        r = s.patch(API + "/repos/%s/%s/git/refs/heads/main" % (owner, name),
                    json={"sha": commit_sha, "force": True}, timeout=60)
    else:
        r = s.post(API + "/repos/%s/%s/git/refs" % (owner, name),
                   json={"ref": "refs/heads/main", "sha": commit_sha}, timeout=60)
    if r.status_code not in (200, 201):
        raise SystemExit("更新 ref 失败：" + r.text[:300])
    print("main 已指向", commit_sha)
    print("仓库：https://github.com/%s/%s" % (owner, name))


if __name__ == "__main__":
    main()
