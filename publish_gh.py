"""把 site/ 推送到 GitHub，触发 Pages 自动发布。

用法：
    .venv\\Scripts\\python.exe publish_gh.py
    .venv\\Scripts\\python.exe publish_gh.py -m "自定义提交说明"

依赖 .env 中的 GITHUB_TOKEN（classic token，勾选 repo 权限）。
token 只在本次 push 的 URL 里临时使用，不会写进 .git/config。
"""
import argparse
import datetime
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core.config import load_env  # noqa: E402


def run(cmd, check=True, quiet=False):
    proc = subprocess.run(cmd, cwd=ROOT, shell=False,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = (proc.stdout or b"").decode("utf-8", "replace").strip()
    if not quiet and out:
        print(out)
    if check and proc.returncode != 0:
        raise SystemExit("命令失败：%s\n%s" % (" ".join(cmd), out))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--message", default=None)
    ap.add_argument("--repo", default=None, help="owner/repo，默认读 .env 的 GITHUB_REPO")
    args = ap.parse_args()

    load_env()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = args.repo or os.environ.get("GITHUB_REPO", "").strip()
    if not token:
        raise SystemExit("缺少 GITHUB_TOKEN，请写入 .env")
    if not repo or "/" not in repo:
        raise SystemExit("缺少 GITHUB_REPO（形如 用户名/仓库名）")

    owner, name = repo.split("/", 1)
    url = "https://x-access-token:%s@github.com/%s/%s.git" % (token, owner, name)

    if not os.path.isdir(os.path.join(ROOT, ".git")):
        print("[git] 初始化仓库")
        run(["git", "init", "-b", "main"])

    run(["git", "config", "user.name", owner], quiet=True)
    run(["git", "config", "user.email", "%s@users.noreply.github.com" % owner], quiet=True)

    # remote 只存干净地址，token 不落盘
    run(["git", "remote", "remove", "origin"], check=False, quiet=True)
    run(["git", "remote", "add", "origin", "https://github.com/%s/%s.git" % (owner, name)],
        quiet=True)

    run(["git", "add", "-A"])
    msg = args.message or "更新站点 %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if run(["git", "status", "--porcelain"], quiet=True):
        run(["git", "commit", "-m", msg])
    else:
        print("[git] 没有变更，仍尝试推送已有提交")

    print("[git] 推送到 %s" % repo)
    run(["git", "push", url, "HEAD:main", "--force"])

    print("\n已推送。Pages 会由 Actions 自动发布：")
    print("  https://%s.github.io/%s/" % (owner.lower(), name.lower()))
    print("  构建进度：https://github.com/%s/%s/actions" % (owner, name))


if __name__ == "__main__":
    main()
