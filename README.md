# PaperMind

> 论文笔记自动化 Agent —— 输入论文，输出结构化 Markdown 笔记。

PaperMind 接受 PDF 文件、arXiv ID/链接、DOI 或论文标题，自动获取全文，调用 DeepSeek LLM 按你定义的 `template.md` 模版填写笔记。

完整设计文档见 [CLAUDE.md](CLAUDE.md)。

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 3. 自定义笔记模版（可选）
#    编辑 template.md，所有 {{字段}} 占位符都会被 LLM 自动填写

# 4. 运行
python main.py --input "2401.12345"                 # 单篇 arXiv
python main.py --input "./paper.pdf"                # 本地 PDF
python main.py --input "Attention Is All You Need"  # 标题搜索
python main.py --batch papers.txt                   # 批量
python main.py --batch papers.txt --output ./notes/ # 指定输出目录
```

## 输入形式

| 形式            | 例子                              |
| --------------- | --------------------------------- |
| 本地 PDF        | `./papers/transformer.pdf`        |
| arXiv ID 或 URL | `2401.12345` / `arxiv.org/abs/…`  |
| DOI             | `10.1145/3442188.3445922`         |
| 论文标题        | `Attention Is All You Need`       |

## 项目结构

详见 [CLAUDE.md](CLAUDE.md)。

## License

MIT
