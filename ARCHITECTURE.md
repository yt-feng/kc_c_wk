# kc_c_wk 架构说明

本仓库用于自动生成《加密货币观察》主刊和独立《专题研究》文档。

## 输出物

每次运行会在 `reports/YYYY/` 下生成：

- `加密货币观察_YYYYMMDD.docx`：主刊 Word。
- `专题研究_YYYYMMDD.docx`：独立专题研究翻译稿。
- `_manifests/加密货币观察_YYYYMMDD.json`：主刊运行记录、入选条目和 fact check 结果。
- `_manifests/专题研究_YYYYMMDD.json`：专题研究选题、PDF 来源、翻译稿和 fact check 结果。
- `research_sources/YYYYMMDD/`：专题研究英文原文 PDF。

## 主刊栏目

主刊《加密货币观察》不再包含【专题研究】栏目，只保留：

- 【政策风向】3 条：优先美国、香港正式监管动向，且 3 条不应全部来自同一地区。
- 【行业前沿】2 条：协议、DeFi、Layer 2、基础设施、互操作、代币化、安全、钱包、质押、升级和产品发布等技术或生态进展。
- 【市场动态】2 条：与【行业前沿】采用同一选题标准，不优先选择 ETF、价格、融资、交易所、并购、资金流等纯市场事件。
- 【意见领袖】2 条：体现人物或机构观点，可使用“XXX认为”“XXX指出”。

主刊新闻时效为最近 7 天，来源排除中文网站。

## 专题研究

专题研究独立生成一个 Word，不进入主刊目录或正文。

要求：

- 检索近 2 个月的英文 PDF 研究报告。
- 优先来源包括 PwC、KPMG、BCG、PitchBook、McKinsey、BIS、Deloitte、EY、Citi、JPMorgan 等全球智库、投行、咨询公司和国际机构。
- 主题限定为 crypto、digital assets、tokenization、stablecoin、blockchain、DeFi、Web3 等。
- 原文 PDF 保存到 `reports/YYYY/research_sources/YYYYMMDD/`。
- 提取 PDF 文本后交给 DeepSeek 编译成中文专题研究稿。
- 目标长度约 15—20 页，按现有 Word 样式排版，普通正文为仿宋 14pt、首行缩进 2 字符、两端对齐、单倍行距并对齐文档网格。

## 生成链路

1. `crypto_observer/main.py` 负责主流程入口。
2. `crypto_observer/sources.py` 负责主刊候选新闻采集、去重、原文链接解析和正文抓取。
3. `crypto_observer/deepseek.py` 负责主刊选题和逐篇全文编译。
4. `crypto_observer/research.py` 负责专题研究 PDF 搜索、下载、文本提取和 DeepSeek 翻译编译。
5. `crypto_observer/docx_writer.py` 负责主刊 Word 排版，也提供专题研究 Word 排版函数。
6. `crypto_observer/factcheck.py` 负责主刊栏目数量、时效、来源、长度、标点和链接检查。
7. `crypto_observer/text_utils.py` 负责中文标点、全角引号等文本清洗。

## GitHub Actions

`.github/workflows/weekly-crypto-observer.yml`：

- 每周三北京时间 13:17 自动运行，确保 16:00 前生成。
- 支持手动 `workflow_dispatch`。
- 成功后自动提交 Word、manifest 和专题研究 PDF 到 repo。

## 环境变量

- `DEEPSEEK_API_KEY`：必需，用于 DeepSeek 编译。
- `DEEPSEEK_MODEL`：可选，默认 `deepseek-v4-flash`。
- `CRYPTO_OBSERVER_DAYS`：主刊新闻回溯天数，默认 3。
- `CRYPTO_OBSERVER_STRICT`：`1` 表示 fact check 错误时失败，`0` 表示保留草稿。
- `CRYPTO_OBSERVER_OUTPUT_ROOT`：默认 `reports`。
- `CRYPTO_OBSERVER_MAX_RAW_ITEMS`：主刊最大候选数。

## 维护注意事项

- 不要把中文站点加入信息源。
- 主刊和专题研究是两个独立输出，专题研究不应出现在主刊目录中。
- Word 样式改动优先集中在 `docx_writer.py`。
- 所有链接应优先使用原站链接，避免 Google News RSS 包装链接。
- 生成后应检查 manifest 中的 `factcheck` 字段。
