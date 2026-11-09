# 官媒议论文日报

每天自动从官媒采集评论/理论文章，用规则识别「总—分—总」结构，每日精选 5 篇，
生成静态站点并通过企业微信群机器人推送到微信。

## 一句话流程

```
08:30 采集 → 抽取正文 → 结构打分 → 跨站判重 → 选题 → 渲染 → 部署
09:00 推送「今日 5 篇 + 站点链接」到企业微信
开机/登录 若当日未推送则立即补推（幂等）
```

## 采集源

| 源 | 入口 | 备注 |
|---|---|---|
| 求是网 | 求是网评 / 社论评论 | 静态 |
| 新华网 | 新华时评 / 新华社评论员 / 新华网评 | 静态，过滤"组图"海报 |
| 中国青年报 | 电子版理论评论版 | 静态，版面号随星期动态探测 |
| 法治日报 | 电子版 02/03/07 版 | 静态（官网正文页有 JS 反爬，故走电子版） |
| 光明日报 | 光明观察 / 评论员专栏 | 静态 |
| 经济日报 | 中国经济网评论频道 | 静态 |
| 人民网 | 观点频道 | **robots 要求 Crawl-delay: 120，严格串行** |
| 半月谈 | 半月谈评论 | 站点连接不稳，失败不影响整体 |
| 人民日报 | 电子版 | 待接入（JS 渲染，需 Playwright） |

## 目录

```
config.yaml        站点/采集/打分/推送配置
.env               webhook、口令、Cloudflare 凭据（勿提交）
run.py             入口
deploy.py          部署到 Cloudflare Pages
adapters/          每个媒体一个适配器
core/
  fetcher.py       按域名限速 + 重试 + 列表页缓存
  extract.py       正文抽取（段落密度法 + 按行切分兜底 + 整版聚合页截取）
  score.py         「总—分—总」四维打分
  dedupe.py        simhash 跨站判重
  pick.py          选题（分数 + 同源上限 + 补位）
  store.py         SQLite 存档
  render.py        静态站生成
  push.py          企业微信推送（4096 字节自动分片）
templates/         Jinja2 模板
static/style.css   样式
data/app.db        存档
site/              生成的静态站
logs/run.log       运行日志
scripts/register_tasks.ps1  注册/卸载计划任务
```

## 常用命令

```bash
# 激活环境（Windows）
.venv\Scripts\python.exe run.py <command>

run.py test-push                  # 发一条测试消息
run.py collect --date 2026-11-09  # 只看候选列表
run.py enrich  --date 2026-11-09  # 抓正文 + 打分，打印排名
run.py build   --date 2026-11-09  # 完整生成（含采集）
run.py rebuild --date 2026-11-09  # 不重新抓取，用库中文章重新选题渲染
run.py daily                      # 补推当日（幂等）
run.py morning-build              # 计划任务 08:30 调用
run.py morning-push               # 计划任务 09:00 调用
run.py catchup                    # 计划任务 开机/登录 调用
```

本地预览：

```bash
.venv\Scripts\python.exe -m http.server 8931 --bind 127.0.0.1 --directory site
# 打开 http://127.0.0.1:8931/
```

## 站点结构

| 路径 | 内容 |
|---|---|
| `/` | 首页：最近 `site.recent_days` 天（默认 10），按天分组，直接列出每天的标题与论点 |
| `/d/{日期}/` | 单期页：当天全部文章，含「立论→分论点→收束」流程条，底部可翻更早/更新一期 |
| `/a/{日期}{序号}/` | 单篇：开篇标黄、分论点标红、收束标绿，页脚有原文链接 |
| `/archive/` | 全部期次列表（超过近 10 天的从这里进） |

首页顶部有日期胶囊（横向滚动），点击直接跳到那一天。

## 结构打分说明

满分 100，四维相加，另有排除项：

| 维度 | 上限 | 判据 |
|---|---|---|
| 开篇立论 | 25 | 首段/次段有明确论点句；标题即观点也计分 |
| 主体论证 | 30 | 小标题式分层，或 ≥2 个分论点且论据覆盖率 ≥40% |
| 结尾收束 | 25 | 收束词 + 首尾关键词呼应 |
| 体量形态 | 15 | 字数 700–3200、段落分布合理 |
| 栏目先验 | +6 | 评论/理论版面加权，封顶 98 |
| 排除 | −35~−40 | 本报讯/记者从…获悉、访谈公告类、篇幅过短 |

≥70 入选；60–70 作为补位（页面会显示结构度）。周日/节假日评论版常停更，
自动回看最近 3 天（`collect.window_days`）。

## 线上站点与推送链接

当前线上地址（WorkBuddy 应用发布，静态快照）：

```
https://comment-daily.app.workbuddy.host/?sharecode=3VM73IMFVB
```

配置写在 `config.yaml` 的 `site.base_url` + `site.share_code`，推送时自动拼成
`{base_url}/d/{日期}/?sharecode=xxx`，并附带首页（往期归档）链接。

⚠️ 这是**静态快照**：本机重新生成 `site/` 后，必须重新发布一次，线上才会更新。
不重新发布时，推送的当期链接会打不开——程序已加探活，检测到当期页 404 时
只推归档首页，不会发死链。

### 要每天全自动上线，走 Cloudflare Pages

1. 注册 Cloudflare 免费账号（不需要信用卡）
2. 生成 API Token：My Profile → API Tokens → 权限 `Cloudflare Pages:Edit`
3. 填入 `.env`：
   ```
   CF_API_TOKEN=...
   CF_ACCOUNT_ID=...
   CF_PROJECT_NAME=ai-comment-daily
   ```
4. 运行 `.venv\Scripts\python.exe deploy.py`，首次会自动创建项目
5. 拿到 `https://xxx.pages.dev` 后写入 `config.yaml` 的 `site.base_url`
   （并把 `share_code` 清空）

之后每天 08:30 的构建会自动上传，链接固定不变。

站点带两层保护：`<meta name="robots" content="noindex">` 与 `_headers` 的
`X-Robots-Tag`，搜索引擎不会收录。

## 定时任务

```powershell
# 注册
powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1

# 卸载
powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1 -Uninstall
```

三个任务：

- `AICmt-DailyBuild` 每天 08:30 —— 采集 + 生成 + 部署
- `AICmt-DailyPush` 每天 09:00 —— 推送
- `AICmt-Catchup` 登录时 —— 当日未推送则立即补推

任务设为「错过则尽快运行」（StartWhenAvailable），配合幂等逻辑：
推送前检查 `editions.status`，已推送则跳过，重启电脑不会重复推送。

> 机器关机时无法推送。真实能力是「开机时 09:00 准点，关机后开机 30 分钟内补推」。

## 合规

- 严格遵守各站 robots.txt，人民网 `Crawl-delay: 120` 不调低
- 内容仅个人学习研究使用，站点不收录于搜索引擎
- 每篇保留标题、媒体、版面、原文链接，正文节选不作全文转载
- 不用于任何商业用途
