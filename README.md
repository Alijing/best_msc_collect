# BEST MSC COLLECT

无状态的小说目录分析与抓取服务。输入目录页 URL，识别章节列表并抓取正文，结果通过 API 返回。可导出为 TXT、JSON 或 CSV。

技术栈是 FastAPI、httpx、lxml / parsel 和 Pydantic v2。任务进度放在内存里；配置了 Redis 时改为 Redis，方便多个 worker 共享。

## 能做什么

- 分析目录页，给出章节容器、条目和下一页的 CSS 选择器
- 只抓目录，或目录加正文一次抓完
- 正文分页会跟着「下一页」走，并清掉常见广告、水印和站点提示
- 未指定正文选择器时，第一章识别一次，后续章节复用
- 按域名限制请求间隔；超时、连接失败以及 403 / 429 / 503 会指数退避重试
- 只允许 http / https，拒绝内网、回环、链路本地地址；跳转会再次检查
- 异步任务可查询进度、分页取章节、删除并取消

不支持浏览器渲染。请求里带 `usePlaywright: true` 会返回 400。

## 目录

```text
app/
├── main.py                     # 入口与生命周期
├── api/                        # HTTP 接口
│   ├── analyze.py              # POST /api/analyze
│   ├── crawl.py                # POST /api/crawl
│   ├── content.py              # POST /api/content
│   ├── extract.py              # POST /api/extract
│   ├── novel.py                # POST /api/novel
│   ├── tasks.py                # GET/DELETE /api/tasks/*
│   ├── export.py               # POST /api/export
│   └── guards.py               # 创建后台任务前的校验
├── core/
│   ├── config.py               # pydantic-settings
│   ├── exception_handlers.py   # 失败时也返回 code / msg / data
│   ├── task_store.py           # 进度、目录、正文分开存放
│   ├── rate_limit.py           # 按域名的请求间隔
│   └── background.py           # 后台任务数量、取消、退出时排空
├── fetcher/                    # httpx 抓取、重试、响应体积上限
├── analyzer/                   # 目录评分、正文识别、分页、清洗
├── services/                   # 分析、目录、正文、全本、导出
├── schemas/                    # 请求体，以及 response.py 里的统一外壳
└── utils/                      # URL 安全检查、文本工具
tests/
requirements.txt
environment.yml
.env.example
```

## 环境

- Python 3.12+
- 可选：Redis。不配置时进度只在当前进程内存中

Conda：

```bash
conda env create -f environment.yml
conda activate best_msc_collect
```

或者用 pip：

```bash
pip install -r requirements.txt
```

复制配置后启动：

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env

uvicorn app.main:app --reload --port 8000
```

交互式文档在 `http://127.0.0.1:8000/docs`。健康检查是 `GET /health`，成功时 `data.status` 为 `ok`。

## 配置

配置来自环境变量或项目根目录的 `.env`。

| 变量                     | 含义                               | 默认值    |
| ------------------------ | ---------------------------------- | --------- |
| `DEBUG`                  | 调试日志                           | `false`   |
| `HTTP_TIMEOUT`           | 请求超时（秒）                     | `15`      |
| `MAX_RESPONSE_SIZE`      | 单个响应上限（字节），超出即中断   | `5242880` |
| `MAX_REDIRECTS`          | 最大跳转次数                       | `5`       |
| `HTTP_RETRY_ATTEMPTS`    | 可重试错误的次数                   | `3`       |
| `HTTP_RETRY_MIN_WAIT`    | 退避最短等待（秒）                 | `1`       |
| `HTTP_RETRY_MAX_WAIT`    | 退避最长等待（秒）                 | `10`      |
| `ALLOW_PRIVATE_IP`       | 是否允许内网地址                   | `false`   |
| `DNS_CACHE_SECONDS`      | 主机解析结果缓存（秒）             | `30`      |
| `REDIS_URL`              | 留空则使用内存                     | 空        |
| `TASK_TTL_SECONDS`       | 任务过期时间（秒），进度更新会顺延 | `3600`    |
| `RATE_LIMIT_PER_DOMAIN`  | 每个域名每秒最多请求数             | `2`       |
| `MAX_PAGES_DEFAULT`      | 目录默认最多翻页数                 | `500`     |
| `DELAY_DEFAULT`          | 目录页最小间隔（秒）               | `0`       |
| `MAX_BACKGROUND_TASKS`   | 同时运行的后台任务数               | `4`       |
| `SHUTDOWN_DRAIN_SECONDS` | 进程退出前等待后台任务的秒数       | `20`      |

`DELAY_DEFAULT` 为 0 时，目录翻页只受域名限速约束。请求里的 `delay` 表示页面之间的最小间隔：限速已经等待过的时间不会再叠加。例如限速是每秒 2 次（间隔 0.5 秒），`delay` 为 2 时，目录页之间大约再多等 1.5 秒。正文抓取只走域名限速，不用这个 `delay`。

## 接口

| 方法   | 路径                            | 说明                                   |
| ------ | ------------------------------- | -------------------------------------- |
| POST   | `/api/analyze`                  | 同步分析一页目录                       |
| POST   | `/api/crawl`                    | 异步抓目录                             |
| POST   | `/api/content`                  | 同步抓一章正文                         |
| POST   | `/api/extract`                  | 用调用方给出的选择器，从一页里抽出链接 |
| POST   | `/api/novel`                    | 异步抓目录，并可选抓正文               |
| GET    | `/api/tasks/{task_id}`          | 进度。不返回章节正文                   |
| GET    | `/api/tasks/{task_id}/chapters` | 分页取章节                             |
| DELETE | `/api/tasks/{task_id}`          | 取消后台任务并删除已存数据             |
| POST   | `/api/export`                   | 把调用方提交的章节导出为文件           |
| GET    | `/health`                       | 健康检查                               |

### 统一响应

除 `POST /api/export` 成功时直接返回文件外，接口（含参数错误、业务错误和未匹配路由）都返回同一个 JSON 对象：

| 字段   | 类型                    | 说明                                                                                 |
| ------ | ----------------------- | ------------------------------------------------------------------------------------ |
| `code` | int                     | 业务状态码，与 HTTP 状态码相同。200 成功，500 为未处理的服务器错误，其他值见下表    |
| `msg`  | string                  | 成功时为 `ok`，失败时为错误描述                                                      |
| `data` | object / array / null   | 业务数据，可以是实体、列表或分页对象。失败时为 `null`                               |

成功：

```json
{ "code": 200, "msg": "ok", "data": {} }
```

失败不再使用 `detail`。例如任务不存在：

```json
{ "code": 404, "msg": "任务不存在或已过期", "data": null }
```

| `code` | 何时出现                         |
| ------ | -------------------------------- |
| 200    | 成功。正文或链接没识别到时也走这里，原因在 `data.error` |
| 400    | URL 不安全，或 `usePlaywright` 为 true，或导出格式不合法 |
| 404    | 任务不存在、已过期，或路径不存在 |
| 422    | 请求参数校验失败，字段说明在 `msg` |
| 429    | 后台任务已满                     |
| 500    | 未处理的服务器错误               |
| 502    | 同步分析、正文抓取或链接提取失败 |

调用方先看 `code`。只有 `code` 为 200 时再读 `data`。

请求体和 `data` 里，多个单词的字段使用驼峰，例如 `taskId`、`containerSelector`、`usePlaywright`。`url`、`status`、`code` 这种单个单词不变。查询参数 `withContent` 也是驼峰。

### POST /api/analyze

```json
{ "url": "https://example.com/book/1/" }
```

成功时 `data` 含最终 URL、`containerSelector`、`itemSelector`（固定为 `a`）、下一页 `nextUrl` / `nextText`、`confidence`，以及最多 8 条 `sampleChapters`。识别失败时选择器为 `null`，`confidence` 为 0，`code` 仍是 200。

```json
{
  "code": 200,
  "msg": "ok",
  "data": {
    "url": "https://example.com/book/1/",
    "containerSelector": "#list",
    "itemSelector": "a",
    "nextUrl": null,
    "nextText": null,
    "confidence": 0.86,
    "sampleChapters": [
      { "title": "第一章", "url": "https://example.com/1.html" }
    ]
  }
}
```

### POST /api/crawl

立即返回 `data.taskId`，目录在后台抓取。

| 字段                 | 默认                | 约束                             |
| -------------------- | ------------------- | -------------------------------- |
| `url`                | 必填                | http / https                     |
| `containerSelector` | 空                  | 空则自动识别，并在后续目录页复用 |
| `itemSelector`      | 空                  | 空则使用 `a`                     |
| `nextUrl`           | 空                  | 仅作为第一页的下一页             |
| `maxPages`          | `MAX_PAGES_DEFAULT` | 1–5000                           |
| `delay`             | `DELAY_DEFAULT`     | 0–10 秒                          |
| `usePlaywright`     | `false`             | `true` 时返回 400                |

```json
{
  "code": 200,
  "msg": "ok",
  "data": { "taskId": "…", "status": "pending" }
}
```

### POST /api/novel

立即返回 `data.taskId`。先抓目录，再按章节抓正文。`data` 的形状与 `/api/crawl` 相同。

在 `/api/crawl` 的字段之外还有：

| 字段                | 默认   | 约束                   |
| ------------------- | ------ | ---------------------- |
| `concurrency`       | `2`    | 1–10，正文阶段的并发   |
| `withContent`      | `true` | `false` 时只返回目录   |
| `followPagination` | `true` | 是否跟随正文分页       |
| `contentSelector`  | 空     | 空则由第一章识别后复用 |
| `clean`             | `true` | 是否清洗正文           |

全本接口没有 `usePlaywright` 字段。

### POST /api/content

同步返回一章。`followPagination` 默认 `true`，`maxPages` 默认 20，范围 1–100。`contentSelector` 一旦传入就必须能匹配，匹配不到时 `code` 仍是 200，原因在 `data.error`，已抓到的前文仍在 `data.content`。

`data` 字段：`url`、`finalUrl`、`title`、`content`、`length`、`pagesCrawled`、`pageUrls`、`error`。

### POST /api/extract

同步。`containerSelector` 必填，`itemSelector` 默认 `a`。选择器没有命中时 `code` 仍是 200，`data.count` 为 0，并带 `data.error`。

`data` 字段：`url`、`count`、`chapters`（`order`、`title`、`url`）、`error`。

### 任务进度

`GET /api/tasks/{task_id}` 的 `data` 只含状态，不含正文。

| status      | stage            | 含义                 |
| ----------- | ---------------- | -------------------- |
| `pending`   | `pending`        | 已创建，尚未开始     |
| `running`   | `catalog`        | 正在抓目录           |
| `running`   | `content`        | 正在抓正文           |
| `completed` | `done`           | 结束                 |
| `failed`    | 保持失败前的阶段 | 出错，原因在 `data.error` |

这些字段都在 `data` 里：`taskId`、`status`、`stage`、`currentPage`、`currentChapter`、`totalChapters`、`chapterCount`、`pagesCrawled`、`error`、`resultAvailable`。

目录阶段看 `currentPage`、`chapterCount`、`pagesCrawled`。正文阶段看 `currentChapter` / `totalChapters`。正文进度大约每 0.5 秒或每 20 章更新一次，最后一章一定会写上，所以轮询时数字可能一次跳多章。

`resultAvailable` 为 true 表示最终结果已经写入。只抓目录时它仍可能是 false，但 `/chapters` 已经能读到当前目录。任务不存在时 `code` 为 404，`data` 为 `null`。

### GET /api/tasks/{task_id}/chapters

| 查询参数       | 默认   | 约束               |
| -------------- | ------ | ------------------ |
| `offset`       | `0`    | ≥ 0                |
| `limit`        | `50`   | 1–500              |
| `withContent` | `true` | `false` 时不读正文 |

`data.total` 是已保存的章节数。抓目录的过程中，这里返回的是截至目前的全部章节，不是最近几十条。`withContent=true` 只读取这一页对应的正文；目录索引（标题和链接）仍会整表加载，用来分页。

`data` 还有 `taskId`、`status`、`stage`、`offset`、`limit`、`withContent`、`chapters`。章节字段：`order`、`title`、`url`。正文完成后还有 `content`、`contentPages`、`contentError`。单章失败不会让整个任务失败，错误写在 `contentError`。`chapters` 为空表示这一页已经到头。

### DELETE /api/tasks/{task_id}

取消正在运行的协程，并删掉进度、目录和正文。之后该任务的写入会被忽略。成功时：

```json
{ "code": 200, "msg": "ok", "data": { "ok": true } }
```

### POST /api/export

导出的是请求体里的 `chapters`，不会按 `taskId` 去存储里取。

```json
{
  "title": "书名",
  "format": "txt",
  "chapters": [
    {
      "order": 1,
      "title": "第一章",
      "url": "https://example.com/1",
      "content": "正文"
    }
  ]
}
```

`format` 为 `txt`、`json` 或 `csv`。成功时响应是附件，不套统一 JSON。`txt` 为 UTF-8，`csv` 为带 BOM 的 UTF-8。文件名含中文时，响应头同时给出 ASCII 兜底名和 `filename*`。`format` 不合法时：

```json
{ "code": 400, "msg": "format 必须是 txt / json / csv", "data": null }
```

## 使用顺序

下面用 curl。Windows 上也可以在 PowerShell 里用 `Invoke-RestMethod`。

先看自动识别是否靠谱：

```bash
curl -s -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"https://example.com/book/1/\"}"
```

`data.sampleChapters` 明显不对时，把看中的选择器传给全本接口：

```bash
curl -s -X POST http://127.0.0.1:8000/api/novel \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"https://example.com/book/1/\", \"containerSelector\": \"#list\", \"itemSelector\": \"a\", \"contentSelector\": \"#content\", \"concurrency\": 2}"
```

`containerSelector` 用来圈定目录，`itemSelector` 默认是 `a`，`contentSelector` 用来锁定正文。识别结果可用就只传 URL：

```bash
curl -s -X POST http://127.0.0.1:8000/api/novel \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"https://example.com/book/1/\", \"concurrency\": 2}"
```

返回：

```json
{ "code": 200, "msg": "ok", "data": { "taskId": "…", "status": "pending" } }
```

轮询进度：

```bash
curl -s http://127.0.0.1:8000/api/tasks/$TASK_ID
```

`data.status` 为 `completed` 后分页取正文。只要 `data.chapters` 为空就说明这一页已经到头：

```bash
curl -s "http://127.0.0.1:8000/api/tasks/$TASK_ID/chapters?offset=0&limit=100"
```

不需要正文时加上 `withContent=false`。把取到的章节放进 `/api/export` 的 `chapters` 即可下载文件。

PowerShell 创建任务：

```powershell
$body = '{"url":"https://example.com/book/1/","concurrency":2}'
$task = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/novel -ContentType "application/json" -Body $body
$task.data.taskId
```

## 抓取时实际发生的事

目录页会给候选容器打分，依据包括章节标题占比、链接 URL 是否同一模板、链接密度、标题长度，以及附近是否有「目录 / 章节列表」这类标题。得分接近时优先更深的容器，并生成 CSS 选择器。下一页优先看 `rel=next` 和「下一页」一类文案。

章节链接先按 URL 模板投票，再按「第 N 章 / Chapter N / 数字标题」过滤。滤掉太多时会退回模板结果，避免漏章。

正文容器偏向长文本、低链接、多段落。提取时保留 `p` 和 `br` 造成的换行，并跳过 `script` / `style`。清洗会去掉收藏提示、网址行、纯符号分隔线等常见噪音。

同一域名的请求共用一个间隔，多本书同时抓也不会互相把等待时间串在一起。解析 HTML 在线程里进行，不占用事件循环。响应按块读取，超过 `MAX_RESPONSE_SIZE` 就停止。跳转到内网地址会失败。主机无法解析时也会失败，而不是放行。

同时运行的 `/api/crawl` 与 `/api/novel` 合计不超过 `MAX_BACKGROUND_TASKS`。进程收到退出信号后，最多等待 `SHUTDOWN_DRAIN_SECONDS`，然后取消仍在跑的任务，再关闭 HTTP 客户端。

## 数据放在哪里

服务不把书籍写入数据库。

- 进度里只有状态、阶段、页码和章节计数
- 目录是标题、链接，以及完成后的 `content_pages` / `content_error`
- 正文按章节序号分开存放

内存最多保留约 200 个任务。超限时先丢掉已经结束的任务，不丢掉仍在 `pending` 或 `running` 的任务。无论内存还是 Redis，超过 `TASK_TTL_SECONDS` 没有更新的任务都会过期。服务重启后，内存中的任务消失；要用 Redis 才能在多个进程之间保留进度。

## 测试

```bash
pytest tests/
```

覆盖目录识别、正文提取与选择器复用、域名限速、进度与正文分离、URL 安全检查、目录失败状态、后台任务的数量限制和取消，以及统一响应结构。

## 注意

- 遵守目标站点的服务条款和 `robots.txt`
- 默认每秒每个域名 2 次请求。需要更慢时增大 `delay` 或减小 `RATE_LIMIT_PER_DOMAIN`
- 大书如果抓取时间可能超过 1 小时，调大 `TASK_TTL_SECONDS`，否则长时间没有进度写入时任务会被清掉
- 抓取结果需要调用方自己保存。导出接口不会替你读取任务存储
