# PaperMind

> 论文笔记自动化 Agent —— 输入论文，输出结构化笔记。

---

## 项目概述

PaperMind 是一个基于 DeepSeek LLM 的论文笔记自动化 Agent。给定一批论文（PDF 文件、arXiv 链接、DOI、或论文标题），Agent 自动获取全文、理解内容，并按照用户提供的 Markdown 模版填写结构化笔记，输出到指定目录。

---

## 项目结构

```txt
papermind/
├── CLAUDE.md              # 本文件，项目说明
├── main.py                # 入口：接收论文列表，驱动整个 pipeline
├── config.py              # 配置：API key、输出路径、重试次数等
├── template.md            # 笔记模版（用户自定义，运行时读取）
│
├── router.py              # Input Router：识别输入类型，分发到对应 fetcher
│
├── fetchers/
│   ├── __init__.py
│   ├── pdf_parser.py      # PDF 文件解析（PyMuPDF）
│   ├── web_fetcher.py     # arXiv / DOI 全文抓取（Unpaywall fallback）
│   └── search_agent.py    # 标题搜索（Semantic Scholar API）
│
├── processor.py           # 文本清洗 + 章节识别 + Chunking
├── llm.py                 # DeepSeek API 调用，结构化 JSON 输出
├── validator.py           # 输出字段完整性校验，触发 retry
├── writer.py              # 将填好的笔记写入目标目录
│
└── outputs/               # 默认笔记输出目录（可在 config 里改）
```

---

## 核心 Workflow

```txt
输入（PDF / arXiv / DOI / 标题）
        ↓
   Input Router          ← 识别类型，选择获取策略
        ↓
  Fetcher（三选一）
  ├── PDF Parser         ← PyMuPDF 提取结构化文本
  ├── Web Fetcher        ← arXiv API / Unpaywall
  └── Search Agent       ← Semantic Scholar API
        ↓
  Text Processor         ← 清洗 + 章节切分 + Chunking
        ↓
  DeepSeek LLM  ←────── template.md（动态读取模版字段）
        ↓
  Output Validator       ← 字段完整性校验，最多 retry 2 次
        ↓
  Writer                 ← 写出 Markdown 笔记到目标目录
```

**两阶段 LLM 调用策略**（应对长文）：

- 第一轮：Abstract + Introduction → 提取研究问题、动机、核心贡献
- 第二轮：Method + Experiment + Conclusion → 提取方法、结果、局限性
- 合并后渲染到模版字段

---

## 快速开始

### 1. 安装依赖

```bash
pip install pymupdf requests httpx openai python-dotenv
```

### 2. 配置

在项目根目录创建 `.env`：

```env
DEEPSEEK_API_KEY=your_key_here
OUTPUT_DIR=./outputs
MAX_RETRIES=2
```

### 3. 准备笔记模版

编辑 `template.md`，定义你想要的笔记字段，例如：

```markdown
# {{title}}

**作者**：{{authors}}
**年份**：{{year}}
**来源**：{{venue}}

## 研究问题

{{research_question}}

## 核心方法

{{method}}

## 主要结论

{{conclusions}}

## 数据集

{{datasets}}

## 个人评价

{{personal_notes}}
```

模版中所有 `{{字段名}}` 都会被 LLM 自动填写。

### 4. 运行

```bash
# 单篇
python main.py --input "2401.12345"

# 批量（文件列表，每行一个）
python main.py --batch papers.txt

# 指定输出目录
python main.py --batch papers.txt --output ./my_notes/2024/
```

---

## 每日速读模式（`--digest`）

除了「指定论文 → 出详细笔记」，PaperMind 还支持「按方向发现新论文 → 过滤相关性 → 压缩 abstract → 出每日清单」。这条流程**不下载 PDF**，只取 arXiv 的 title/author/abstract，快且省。

### 用法

```bash
# 用默认分类（DIGEST_CATEGORIES）+ 近 1 天
python main.py --digest

# 自定义分类与时间窗
python main.py --digest --categories "cs.LG,cs.AI,q-fin.ST" --days 3
```

输出：`outputs/digest_YYYY-MM-DD.md`（Markdown 清单）+ 同名 `.html` + `outputs/latest.html`（双击用浏览器看，断网可用）。条目含相关度星级、命中理由、中文要点，按相关度排序。

### 研究画像

相关性过滤依据 `digest_profile.md`（运行时动态读取，描述「我关注什么」）。该文件含个人信息，已 gitignore；仓库只提交模版 `digest_profile.example.md`。首次使用：复制 example 为 `digest_profile.md` 并改成自己的方向。缺失时自动回退到 example。

相关配置（`.env`，均可选）：

```env
DIGEST_CATEGORIES=cs.LG,cs.AI,cs.CL,q-fin.ST,stat.ML
DIGEST_DAYS=1
```

### 全自动（macOS launchd）

```bash
bash scripts/install_digest.sh    # 安装定时任务
```

每天 9/13/19 点各触发一次，脚本幂等（当天已生成则跳过），早上没网失败时中午/晚上联网自动补跑。卸载：

```bash
launchctl unload ~/Library/LaunchAgents/com.papermind.digest.plist
rm ~/Library/LaunchAgents/com.papermind.digest.plist
```

`scripts/` 下：`run_digest.sh`（被定时调用的 wrapper）、`com.papermind.digest.plist.template`（不含本机路径的 launchd 模版，安装时生成真实 plist）、`install_digest.sh`（安装脚本）。

---

## 模块说明

### `router.py` — Input Router

识别输入类型并分发：

| 输入形式                       | 识别规则           | 分发到         |
| ------------------------------ | ------------------ | -------------- |
| 本地文件路径 / `.pdf` 结尾     | `os.path.exists()` | `pdf_parser`   |
| arXiv URL 或 `XXXX.XXXXX` 格式 | 正则匹配           | `web_fetcher`  |
| `10.` 开头（DOI）              | 前缀匹配           | `web_fetcher`  |
| 其他字符串                     | fallback           | `search_agent` |

### `fetchers/` — 获取器

- `pdf_parser.py`：用 PyMuPDF 提取文本，保留章节标题层级，去除页眉页脚噪声
- `web_fetcher.py`：arXiv 直接拿 PDF；DOI 先查 Unpaywall，失败则尝试 Sci-Hub mirror（需用户自行配置）
- `search_agent.py`：调用 Semantic Scholar `/paper/search` 接口，返回最匹配论文的元数据 + 摘要 + open access PDF 链接

### `processor.py` — 文本处理

```python
def process(raw_text: str) -> dict[str, str]:
    # 1. 清洗：去除参考文献、图表说明、页码
    # 2. 章节识别：按 Abstract / Introduction / Method /
    #              Experiment / Conclusion 切分
    # 3. 返回 {"abstract": ..., "intro": ..., "method": ..., ...}
```

### `llm.py` — DeepSeek 调用

使用 DeepSeek `deepseek-chat` 模型，强制 JSON 输出：

```python
def fill_template(sections: dict, template_fields: list[str]) -> dict:
    # System prompt 包含模版字段定义
    # User prompt 包含论文各章节内容
    # response_format={"type": "json_object"}
    # 返回 {字段名: 填写内容} 的字典
```

### `validator.py` — 字段校验

```python
def validate(filled: dict, required_fields: list[str]) -> tuple[bool, list[str]]:
    # 返回 (是否通过, 缺失字段列表)
    # 缺失字段会作为 retry prompt 的补充指令
```

### `writer.py` — 笔记写出

- 将填好的字段渲染回 `template.md` 格式
- 文件名规则：`{year}_{first_author}_{short_title}.md`
- 支持按年份、主题等子目录写入（通过 `--output` 参数指定）

---

## 依赖清单

| 库                   | 用途                                            |
| -------------------- | ----------------------------------------------- |
| `pymupdf`            | PDF 文本提取                                    |
| `requests` / `httpx` | HTTP 请求（arXiv、Unpaywall、Semantic Scholar） |
| `openai`             | DeepSeek API（兼容 OpenAI SDK）                 |
| `python-dotenv`      | 读取 `.env` 配置                                |

---

## 注意事项

- DeepSeek API 使用 OpenAI 兼容接口，`base_url` 设为 `https://api.deepseek.com`
- 论文全文超长时自动启用两阶段 chunking，无需手动干预
- `template.md` 运行时动态读取，修改模版后无需重启，下次运行即生效
- 输出目录不存在时自动创建
- 批量处理时单篇失败不影响其他论文，错误会记录到 `outputs/errors.log`
