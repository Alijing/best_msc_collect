# Best MSC Collect Service

基于 Flask + Selenium（v1） / Flask + Scrapling（v2） 的网页数据采集服务，提供 HTTP API 接口用于自动化网页操作和数据提取。

## 项目结构

```
best_msc_collect/
├── requirements.txt                               # 项目依赖
├── run.py                                         # 启动脚本
├── README.md                                      # 项目说明文档
└── best_msc_collect/                              # 主应用目录
    ├── __init__.py                                # 包初始化文件
    ├── app.py                                     # Flask 应用创建
    ├── config/                                    # 配置文件
    │   └── default.py                             # 默认配置
    ├── models/                                    # 数据模型
    │   └── unified_model.py                       # 统一数据模型
    ├── routes/                                    # 路由处理
    │   ├── api.py                                 # v1 API 路由（Selenium）
    │   └── v2_api.py                              # v2 API 路由（Scrapling）
    ├── services/                                  # 业务逻辑层
    │   ├── __init__.py                            # v1 服务包初始化文件
    │   ├── novel_crawl_service.py                 # v1 小说爬虫服务
    │   ├── video_preview_service.py               # v1 视频预览服务
    │   └── v2/                                    # v2 服务包（Scrapling）
    │       ├── __init__.py                        # v2 服务包初始化文件
    │       ├── novel_crawl_service.py             # v2 小说爬虫服务
    │       └── video_preview_service.py           # v2 视频预览服务
    └── utils/                                     # 工具类
        ├── web_collector.py                       # v1 网页数据收集器（Selenium）
        └── scrapling_collector.py                 # v2 网页数据收集器（Scrapling）
```

## 功能特点

- 提供 RESTful API 接口
- 支持自定义网页操作流程
- 可配置的数据提取规则
- 支持无头浏览器模式
- 详细的日志记录
- 支持多层级页面数据抓取
- 支持分页数据自动抓取

## 环境要求

- Python 3.7+
- Google Chrome 浏览器
- ChromeDriver（与 Chrome 版本匹配）

## 安装步骤

1. 进入项目目录：

   ```bash
   cd best_msc_collect
   ```

2. 创建conda环境（推荐）：

   ```bash
   conda create -n best_msc_collect python=3.8
   ```

3. 激活conda环境：

   ```bash
   conda activate best_msc_collect
   ```

4. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

## 配置说明

在 `best_msc_collect/config/default.py` 中可以修改默认配置：

- `CHROMEDRIVER_PATH`: ChromeDriver 路径
- `LOG_LEVEL`: 日志级别
- `LOG_FILE`: 日志文件路径
- `HOST`: 服务监听地址
- `PORT`: 服务监听端口
- `DEBUG`: 是否开启调试模式
- `PREVIEW_CONFIG`: 预设的基础配置（preview_url、chromedriver_path、headless）
- `WEB_DATA_COLLECT_CONFIG`: 预设的基础配置（chromedriver_path、headless）

也可以通过环境变量覆盖这些配置：

- `CHROMEDRIVER_PATH`: ChromeDriver 路径
- `LOG_LEVEL`: 日志级别
- `LOG_FILE`: 日志文件路径
- `HOST`: 服务监听地址
- `PORT`: 服务监听端口
- `DEBUG`: 是否开启调试模式
- `PREVIEW_URL`: 预览目标网址
- `PREVIEW_HEADLESS`: 是否使用无头模式

## 启动服务

```bash
python run.py
```

服务默认在 `http://127.0.0.1:5000` 启动。

## API 接口

### 1. 健康检查

```
GET /api/health
```

响应示例：

```json
{
  "status": "healthy",
  "message": "Web Preview Service is running"
}
```

### 2. 视频预览（使用预设配置）

```
POST /api/video/preview
Content-Type: application/json
```

请求体示例：

```json
{
  "data_field": "videoPreview",
  "actions": [
    {
      "type": "fill",
      "selector": ".magnet-input",
      "value": "magnet:?xt=urn:btih:394ea1d4fb4ada84401ba6fc8a95957f984ca6f4"
    },
    {
      "type": "click",
      "selector": ".preview-button"
    }
  ],
  "data_extraction": [
    {
      "field": "imageUrls",
      "method": "attribute",
      "selector": ".thumb-item img",
      "attribute": "src"
    }
  ]
}
```

响应示例：

```json
{
  "data": {
    "videoPreview": [
      {
        "imageUrls": "https://whatslink.info/image/68ad4f22ce81c22012b112b7ef45a335"
      },
      {
        "imageUrls": "https://whatslink.info/image/c2161a575939067d630d8b9d358559dc"
      },
      {
        "imageUrls": "https://whatslink.info/image/b015c57e589136aaa28764f5a1bbc3a8"
      },
      {
        "imageUrls": "https://whatslink.info/image/e7a3f31095e2b26c639d79754f62be29"
      },
      {
        "imageUrls": "https://whatslink.info/image/9325d83a62db7640677b088da997723e"
      }
    ]
  },
  "success": true
}
```

### 3. 小说列表和详情页数据采集

```
POST /api/novel/crawl
Content-Type: application/json
```

请求体示例：

```json
[
  {
    "url": "https://www.biqugie.com/read/1651/",
    "data_field": "chapters",
    "next_page_selector": ".listpage .right a",
    "actions": [],
    "data_extraction": [
      {
        "field": "title",
        "method": "text",
        "selector": ".panel-chapterlist dd a"
      },
      {
        "field": "link",
        "unique": true,
        "method": "attribute",
        "selector": ".panel-chapterlist dd a",
        "attribute": "href"
      }
    ],
    "lower_level_page_config": [
      {
        "url": "link",
        "data_field": "contents",
        "actions": [],
        "next_page_selector": null,
        "data_extraction": [
          {
            "field": "content",
            "method": "text",
            "selector": "#content"
          }
        ],
        "lower_level_page_config": null
      }
    ]
  }
]
```

响应示例：

```json
{
  "data": {
    "chapters": [
      {
        "contents": [
          {
            "content": "第一章 龙城苏家 灾变，地球气候的剧烈变化，令整个世界进入了冰冻期，人口锐减，资源匮乏，家园毁灭...."
          }
        ],
        "link": "https://www.biqugie.com/1/1651/360651.html",
        "title": "第一章 龙城苏家"
      }
    ]
  },
  "success": true
}
```

## v2 接口（基于 Scrapling 引擎）

v2 在 v1 基础上完全替换抓取引擎为 [Scrapling](https://github.com/D4Vinci/Scrapling)，提供更强的反爬能力与更高的性能。**v1 与 v2 并行运行**，调用方可按需选择。

### v1 vs v2 对比

| 维度         | v1                                   | v2                                         |
| ------------ | ------------------------------------ | ------------------------------------------ |
| 引擎         | Selenium + ChromeDriver              | Scrapling（Playwright + curl_cffi）        |
| 反爬         | 无                                   | 内置 Cloudflare Turnstile 绕过             |
| 抓取速度     | 慢（需启动浏览器）                   | 快（`fetcher` 模式纯 HTTP，毫秒级）        |
| 自适应选择器 | 无                                   | `adaptive=True`（网站改版自动迁移）        |
| 选择器       | 仅 CSS                               | CSS / XPath / 文本 / 正则                  |
| 分页最大数   | 硬编码 2 页                          | `SCRAPLING_MAX_PAGES=50`                   |
| 下级最大数   | 硬编码 2 条                          | `SCRAPLING_MAX_CHILDREN=100`               |
| 入参副作用   | `video_preview_service` 直接修改 url | 用 `model_copy(deep=True)` 拷贝后再改      |
| 返回结构     | `{success, data}`                    | + `version` / `elapsed_ms` / `total_items` |

### v2 配置项

在 `best_msc_collect/config/default.py` 中可修改：

| 配置项                   | 默认值     | 含义                                             |
| ------------------------ | ---------- | ------------------------------------------------ |
| `SCRAPLING_FETCHER`      | `stealthy` | 默认 fetcher：`fetcher` / `dynamic` / `stealthy` |
| `SCRAPLING_HEADLESS`     | `True`     | 浏览器是否无头模式                               |
| `SCRAPLING_NETWORK_IDLE` | `True`     | 是否等待网络空闲后再返回                         |
| `SCRAPLING_ADAPTIVE`     | `True`     | 是否启用自适应选择器                             |
| `SCRAPLING_PROXY`        | `None`     | 代理地址，如 `http://127.0.0.1:7890`             |
| `SCRAPLING_MAX_PAGES`    | `50`       | 分页抓取最大页数                                 |
| `SCRAPLING_MAX_CHILDREN` | `100`      | 下级页面最大处理数                               |
| `SCRAPLING_TIMEOUT`      | `30`       | 单次请求超时秒数                                 |

支持环境变量覆盖：`SCRAPLING_FETCHER`、`SCRAPLING_HEADLESS`、`SCRAPLING_NETWORK_IDLE`、`SCRAPLING_ADAPTIVE`、`SCRAPLING_PROXY`、`SCRAPLING_MAX_PAGES`、`SCRAPLING_MAX_CHILDREN`、`SCRAPLING_TIMEOUT`。

### v2 API 接口

#### 1. 健康检查

```
GET /api/v2/health
```

响应示例：

```json
{
  "status": "healthy",
  "version": "v2",
  "message": "Best MSC Collect Service v2 is running (Scrapling engine)"
}
```

#### 2. 视频预览

```
POST /api/v2/video/preview
Content-Type: application/json
```

请求体格式与 v1 `/api/video/preview` 一致（不必传 `url`，由服务从 `SCRAPLING_CONFIG.preview_url` 注入）：

```json
{
  "data_field": "videoPreview",
  "actions": [
    {
      "type": "fill",
      "selector": ".magnet-input",
      "value": "magnet:?xt=urn:btih:..."
    },
    { "type": "click", "selector": ".preview-button" }
  ],
  "data_extraction": [
    {
      "field": "imageUrls",
      "method": "attribute",
      "selector": ".thumb-item img",
      "attribute": "src"
    }
  ]
}
```

响应示例：

```json
{
  "success": true,
  "version": "v2",
  "elapsed_ms": 3421,
  "data": {
    "videoPreview": [
      {
        "imageUrls": "https://whatslink.info/image/68ad4f22ce81c22012b112b7ef45a335"
      }
    ]
  }
}
```

#### 3. 小说列表和详情页数据采集

```
POST /api/v2/novel/crawl
Content-Type: application/json
```

请求体格式与 v1 `/api/novel/crawl` 一致，v2 新增 `xpath` / `regex` 两种 `method`：

```json
[
  {
    "url": "https://www.biqugie.com/read/1651/",
    "data_field": "chapters",
    "next_page_selector": ".listpage .right a",
    "actions": [],
    "data_extraction": [
      {
        "field": "title",
        "method": "text",
        "selector": ".panel-chapterlist dd a"
      },
      {
        "field": "link",
        "unique": true,
        "method": "attribute",
        "selector": ".panel-chapterlist dd a",
        "attribute": "href"
      }
    ],
    "lower_level_page_config": [
      {
        "url": "link",
        "data_field": "contents",
        "actions": [],
        "data_extraction": [
          { "field": "content", "method": "text", "selector": "#content" }
        ]
      }
    ]
  }
]
```

响应示例：

```json
{
  "success": true,
  "version": "v2",
  "elapsed_ms": 12834,
  "total_items": 100,
  "data": {
    "chapters": [
      {
        "contents": [{ "content": "第一章 龙城苏家 ..." }],
        "link": "https://www.biqugie.com/1/1651/360651.html",
        "title": "第一章 龙城苏家"
      }
    ]
  }
}
```

### v2 新增能力

#### 1. XPath 与正则提取

`data_extraction[].method` v1 仅支持 `text` / `attribute`，v2 新增：

| method      | 说明                     | 备注                                       |
| ----------- | ------------------------ | ------------------------------------------ |
| `text`      | 元素文本                 | v1 兼容                                    |
| `attribute` | 元素属性                 | v1 兼容，需指定 `attribute` 字段           |
| `xpath`     | XPath 表达式             | v2 新增                                    |
| `regex`     | 对页面原始文本按正则提取 | v2 新增，`selector` 字段复用为正则 pattern |

#### 2. 自适应选择器

`SCRAPLING_ADAPTIVE=True` 时，Scrapling 会记录元素的多维指纹（位置、属性、文本相似度）。当 CSS 选择器失效时，自动在 DOM 中寻找最相似的元素，避免网站改版后整个服务崩溃。

## 日志查看

服务运行过程中会生成详细的日志文件 `web_data_collection.log`，可用于问题诊断和调试。

## 许可证

MIT License
