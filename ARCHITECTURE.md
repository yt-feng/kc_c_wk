# kc_c_wk 架构说明

本仓库用于自动生成《加密货币观察》主刊和独立《专题研究》文档。当前代码以用户提供的 2026 年第 1—10 期样刊为目标格式和编辑标准。

## 输出物

每次运行会在 `reports/YYYY/` 下生成：

- `加密货币观察_YYYYMMDD.docx`：主刊 Word。
- `专题研究_YYYYMMDD.docx`：独立专题研究翻译稿。
- `_manifests/加密货币观察_YYYYMMDD.json`：主刊运行记录、入选条目和 fact check 结果。
- `_manifests/专题研究_YYYYMMDD.json`：专题研究选题、PDF 来源、翻译稿和 fact check 结果。
- `research_sources/YYYYMMDD/`：专题研究英文原文 PDF。

## 样刊目标

样刊的共同结构如下：

1. 目录页按栏目列出文章标题：
   - 【政策风向】3 篇
   - 【行业前沿】2 篇
   - 【市场动态】2 篇
   - 【意见领袖】2 篇
   - 【专题研究】1 篇（当前系统已按用户最新需求拆分为独立 Word，因此主刊不再写入专题研究正文）
2. 每篇文章结构为：
   - 中文标题
   - 2—3 条关键点
   - 6—10 段完整中文编译正文
   - 右对齐信息来源行：`（信息来源：XXX）`
   - 原文标题、原文链接
3. 正文不是摘要，也不是模型扩写评论，而是基于原文事实链条的完整中文编译。典型正文应覆盖背景、机制、监管/市场含义、未决问题或后续程序。
4. 标题应像样刊一样直接概括核心事实，例如“香港证监会试点经认可代币化投资产品二级市场交易”“Ripple、摩根大通与万事达卡完成首笔代币化美债跨境结算”。避免逗号式两段标题、价格预测软文标题和空泛标题。
5. 信息来源必须是原始媒体或机构，不得出现 Bing News、Google News、GDELT 等发现渠道。

## 主刊栏目编辑标准

主刊《加密货币观察》保留四个常规栏目：

- 【政策风向】3 条：监管、立法、法院、官方指南、牌照、正式征询或明确政策进展。优先美国、香港，但 3 篇不能全是同一地区，至少 1 篇与美国相关。
- 【行业前沿】2 条：协议升级、代币化结算、DeFi、RWA、跨链、预言机、钱包、安全、验证者、支付基础设施等技术或产品进展。
- 【市场动态】2 条：融资、并购、IPO、交易产品、机构采用、收入、稳定币供给、预测市场、交易所和市场基础设施等商业动态。不能用纯价格预测凑数。
- 【意见领袖】2 条：必须体现人物或机构观点，正文应自然写出“XXX认为”“XXX指出”“XXX警告”“XXX表示”等观点归属。

主刊新闻时效为最近 7 天，来源排除中文网站。

## 专题研究

专题研究独立生成一个 Word，不进入主刊目录或正文。

要求：

- 只选择一篇近 2 个月内有明确日期证据的英文 PDF 研究报告。
- 不得拼接多篇报告，也不得把短新闻或营销白皮书扩写成研究报告。
- 优先来源包括 PwC、KPMG、BCG、PitchBook、McKinsey、BIS、Deloitte、EY、Citi、JPMorgan、Coinbase Institutional、Chainalysis、Galaxy、CoinShares 等全球智库、投行、咨询公司和研究机构。
- 主题限定为 crypto、digital assets、tokenization、stablecoin、blockchain、DeFi、Web3 等。
- 英文原文 PDF 必须保存到 `reports/YYYY/research_sources/YYYYMMDD/`。
- 提取 PDF 文本后分块交给 DeepSeek 编译成中文专题研究稿。
- 目标长度约 15—20 页，至少 24 段、约 12000 个中文字符。

## 生成链路

1. `crypto_observer/main.py` 负责主流程入口。
2. `crypto_observer/sources.py` 负责主刊候选新闻采集、去重、原文链接解析和正文抓取。
3. `crypto_observer/deepseek.py` 负责按样刊标准进行主刊选题和逐篇编译。
4. `crypto_observer/research.py` 负责专题研究 PDF 搜索、下载、文本提取和 DeepSeek 翻译编译。
5. `crypto_observer/docx_writer.py` 负责主刊 Word 排版，也提供专题研究 Word 排版函数。
6. `crypto_observer/factcheck.py` 负责主刊栏目数量、时效、来源、长度、标点和链接检查。
7. `crypto_observer/text_utils.py` 负责中文标点、全角引号等文本清洗。

## 质量门控

- 每个 URL、标题指纹、正文指纹只能使用一次。
- 阻断 CSS、字体、许可证、搜索包装页、价格预测软文、中文来源和非原始来源。
- 信息来源若为 Bing News、Google News、GDELT，直接判错。
- 主刊栏目数量不足、专题研究长度不足、专题研究 PDF 过旧或缺少 PDF 原文时，strict 模式直接失败。
- 生成稿应宁缺毋滥，失败比提交垃圾稿更可接受。

## GitHub Actions

`.github/workflows/weekly-crypto-observer.yml`：

- 每周三北京时间 09:43、11:53、13:07、14:23 错峰尝试，降低 GitHub 定时任务延迟或漏触发造成的影响。
- 每次定时运行先同步 `main`，校验当天 DOCX 的 Word 文件结构和 manifest 的 fact check；已有有效产物时直接跳过。
- 并发队列确保同一时间只运行一个生成任务，避免多个延迟触发并行覆盖同一天的报告。
- 提交步骤只暂存当期文件，随后从远端 `main` 再次验证；artifact 上传失败不会阻断报告提交。
- 支持手动 `workflow_dispatch`。
- 成功后自动提交 Word、manifest 和专题研究 PDF 到 repo。

## 环境变量

- `DEEPSEEK_API_KEY`：必需，用于 DeepSeek 编译。
- `DEEPSEEK_MODEL`：可选，默认 `deepseek-v4-flash`。
- `CRYPTO_OBSERVER_DAYS`：主刊新闻回溯天数，默认 7。
- `CRYPTO_OBSERVER_STRICT`：`1` 表示 fact check 错误时失败，`0` 表示保留草稿。
- `CRYPTO_OBSERVER_OUTPUT_ROOT`：默认 `reports`。
- `CRYPTO_OBSERVER_MAX_RAW_ITEMS`：主刊最大候选数，默认 500。

## 维护注意事项

- 不要把中文站点加入信息源。
- 主刊和专题研究是两个独立输出，专题研究不应出现在主刊目录中。
- Word 样式改动优先集中在 `docx_writer.py`。
- 所有链接应优先使用原站链接，避免 Google News RSS 包装链接。
- 生成后应检查 manifest 中的 `factcheck` 字段。
