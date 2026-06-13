# kc-m-a 项目聊天历史与交接文档

> 生成时间：2026-06-13  
> 用途：帮助新的 AI 或开发者快速接管 `yt-feng/kc-m-a` 项目。  
> 说明：本文件基于本聊天中可见的历史请求、截图描述、报错日志、已执行的 GitHub 修改与提交记录整理。由于聊天上下文中有部分早期内容被系统压缩为 `Skipped messages`，本文不是逐字逐句 transcript，而是尽量完整的项目需求、迭代过程、现状与待办清单。

---

## 1. 项目总目标

用户希望在 GitHub repo `yt-feng/kc-m-a` 中建设两个相关但独立的自动化任务：

1. **Weekly M&A cases：每周并购案例 Excel**
   - 每周抓取最近 1 周全球并购案例，**中国为主、全球为辅**。
   - 参考用户上传 Excel 的形式输出 `.xlsx`。
   - Excel A 列“案例分类”必须参考 Word《并购分类建议（含案例名称）》中的 10 大并购分类。
   - 重点抓取中国信息源，同时全球信息源参考 Google News。
   - 用 DeepSeek API 将新闻/公告候选结构化到表格。
   - DeepSeek API key 已放在 repo Secret。
   - 由 GitHub Action 定时自动运行，输出 Excel 并保存到 repo。

2. **Weekly M&A case reports：每周并购案例分析报告 Word**
   - 每周生成 4 篇并购案例分析报告，**中国为主**，每周至少 2 篇国内案例。
   - 每篇文章输出为 `.docx`，按 10 大并购分类进入对应 folder，尽量保持分类文件数量均衡，SPAC 可少一些。
   - 文章面向有并购需求的企业决策者，尤其是上市公司董事长/CEO 类型读者，但正文中不能直接写“上市公司 CEO”。
   - 文章目标是提供启示、经验、教训与并购方法论，不是新闻摘要或广告文。
   - 需要支持一次性回溯近 2 年已完成案例；经典、典型、规模大或明星案例可不限时间。

---

## 2. 当前 repo 与关键路径

### 2.1 Excel 周度追踪

- Workflow：`.github/workflows/weekly-mna.yml`
- Python 入口：`mna_weekly_tracker/main.py`
- Excel 写入：`mna_weekly_tracker/excel.py`
- DeepSeek 结构化：`mna_weekly_tracker/deepseek.py`
- 信息源编排：`mna_weekly_tracker/sources_rich.py`
- 具体抓取器：`mna_weekly_tracker/sources_fixed.py`
- 配置与分类：`mna_weekly_tracker/config.py`
- 输出目录：`outputs/`
- 文件名格式：`并购案例一览_YYYYMMDD_YYYYMMDD.xlsx`

### 2.2 Word 案例报告

- Workflow：`.github/workflows/weekly-mna-reports.yml`
- One-off 预览 workflow：`.github/workflows/one-off-mna-report-preview.yml`
- Python 入口：`mna_case_reports/main.py`
- 选题：`mna_case_reports/case_selection.py`
- 文章生成：`mna_case_reports/report_generation.py`
- 叙事计划：`mna_case_reports/narrative_generation.py`
- 事实包：`mna_case_reports/fact_pack.py`
- 质量校验：`mna_case_reports/article_quality.py`
- 规则与后处理：`mna_case_reports/article_rules_extra.py`
- Word 写入：`mna_case_reports/docx_writer.py`
- Word 格式校验：`mna_case_reports/docx_validate.py`
- 输出目录：`case_reports/`
- 预览输出目录：`case_reports_preview/`

### 2.3 文档

- 已有交接/架构文档：
  - `docs/kc_m_a_handoff_summary.md`
  - `docs/mna_case_reports_architecture.md`
- 本文件建议保存为：
  - `docs/chat_handoff_history_2026-06-13.md`

---

## 3. 当前定时任务设置

### 3.1 Weekly M&A cases（Excel）

当前设定：**北京时间每周五 05:00**。

GitHub Actions cron：

```yaml
- cron: "0 21 * * 4"
```

含义：UTC 每周四 21:00 = 北京时间每周五 05:00。

### 3.2 Weekly M&A case reports（Word 报告）

最初曾设为每周三，后来改为北京时间每周一 06:00，最后用户又要求改为和 Excel 一样：**北京时间每周五 05:00**。

当前设定应为：

```yaml
- cron: "0 21 * * 4"
```

注意：为了触发调试，workflow 中一度添加过 `push` 触发。后续稳定后可考虑删除 `push` 触发，只保留 `schedule` 与 `workflow_dispatch`。

---

## 4. 10 大并购分类

Excel A 列与报告分类 folder 均围绕以下 10 类：

1. 整合一级资产+资本化
2. 依托上市平台持续整合同类资产
3. 上市公司控股权并购
4. 重组上市（借壳，含类借壳）
5. 破产重整
6. 跨境并购
7. 私有化+境内上市
8. SPAC
9. 上市公司+PE
10. 分拆上市

用户要求：每周报告生成时，尽量保证 10 类均衡出现，避免每次都是同一分类下的文章。

---

## 5. Excel 周度并购案例：需求与迭代历史

### 5.1 初始需求

- 每周自动整理最新全球并购案例。
- 中国为主，全球为辅。
- 输出 Excel。
- Excel 格式参考附件。
- A 列“案例分类”参考 Word《并购分类建议（含案例名称）》。
- 重点信息源来自用户截图中的中国信息源。
- 全球信息源参考 Google News。
- DeepSeek API 结构化。
- DeepSeek API key 已放在 repo Secret。
- GitHub Action 自动运行并保存 Excel。
- 每周一个新 Excel，只要最近 1 周信息。

### 5.2 信息源增强

用户反馈“中国并购 deal flow 太少”，要求补充中国新闻源与类似 Google News 的中国 RSS，特别希望覆盖微信等封闭内容生态。

已增加或讨论过的信息源方向：

- 巨潮资讯网 CNINFO 公告 API
- 上交所并购重组/公告
- 深交所公告
- 北交所公告
- 全国股转系统/新三板公告
- Bing News RSS 中文新闻
- Google News 中文新闻
- 搜狗微信搜索（best-effort，可能受限/反爬）
- GDELT DOC API
- 港交所 HKEXnews
- 中东主权基金/产业资本海外并购信息源

### 5.3 搜狗、GDELT 抓取问题

用户曾问日志中搜狗、GDELT 是否真的抓了。后续实现中：

- `sources_rich.py` 对 GDELT 加了 fallback：GDELT 无结果时回退到 Google/Bing News。
- `sources_rich.py` 对搜狗微信加了 diagnostics：若 0 条则记录日志，说明 Sogou Weixin 为 best-effort，可能被 provider 限速。

### 5.4 Excel 链接问题

用户上传了 `并购案例一览_20260605_20260612.xlsx`，反馈：

1. 链接不能点击。
2. 后来又反馈：链接不是原始链接，打不开。

已做过两轮修复：

#### 第一轮：把 URL 列变为可点击 hyperlink

文件：`mna_weekly_tracker/excel.py`  
commit：`48b6ca17adf9d979e6122dbd803f6e75fd49fd30`

改动：

- `周度并购案例` sheet 的 `URL` 列设置为 Excel hyperlink。
- `跟踪信息源` sheet 的 `URL` 列设置为 hyperlink。
- `原始候选` sheet 的 `URL` 列设置为 hyperlink。
- 如果一个单元格中有多个 URL，Excel 只能绑定一个链接，代码保留完整文本，但点击目标取第一个 URL。
- 链接显示为蓝色下划线。

#### 第二轮：尝试将 Google/Bing/Sogou wrapper URL 解析为原始文章 URL

文件：`mna_weekly_tracker/sources_fixed.py`  
commit：`f96fb42a480da636bc0deec0428e7eee16f8807f`

改动：

- 新增 `resolve_original_url()`。
- 对 Google News、Bing、Sogou 微信等 wrapper URL 做 best-effort 解析：
  - 先从 query 参数中提取 `url/u/q/target/to` 等真实链接。
  - 若不是直接参数，则请求 wrapper URL，跟随 redirect。
  - 若 final URL 仍是 wrapper，则从 HTML 中找 canonical、og:url 或第一个非 wrapper URL。
- `rss_items()` 中对 RSS entry link 调用 `resolve_original_url()`。
- `fetch_sogou_weixin()` 中也对搜狗微信链接调用 `resolve_original_url()`。

### 5.5 当前 Excel 链接问题的未确认状态

用户在要求“跑一下”后又转为要求整理历史文档，因此**最新的 Excel 链接修复是否已经通过新运行验证，尚未确认**。

后续接手者应做：

1. 手动运行 `Weekly M&A cases` workflow。
2. 下载/查看新生成的 `outputs/并购案例一览_*.xlsx`。
3. 检查：
   - `周度并购案例.URL`
   - `原始候选.URL`
   - `跟踪信息源.URL`
4. 确认是否仍存在以下 wrapper 域名：
   - `news.google.com`
   - `www.bing.com/news`
   - `weixin.sogou.com/link`
5. 若仍不满足，应增加一个 URL 校验/清洗 step：
   - 对 wrapper URL 做二次解析。
   - 无法解析时，在 Excel 中增加 `原始链接解析状态` 或 `来源入口链接` 与 `原始文章链接` 两列，避免把不可打开链接误认为原文链接。

---

## 6. Word 并购案例分析报告：需求与迭代历史

### 6.1 初始报告需求

用户要求新增一个 action，最好新 folder，但与 Excel 项目相关。

每周输出：

- 4 篇并购案例分析报告。
- 中国为主，每周至少 2 篇国内案例。
- 每篇不超过 4000 中文字，后续调整为 3500–4000 中文字。
- 输出 Word。
- 不要表格。
- 格式参考用户附件 JSON/截图/Word。
- 选题需要对有并购需求的人有启示、教训、经验。
- 10 大分类各建一个 folder，文件数量均衡，SPAC 可少一些。
- 除了每周更新，先跑一次 2 年回溯；最近 2 年完成的新案例都可以，经典代表性案例不限时间。

### 6.2 文章结构初始要求

用户最初给的结构方向：

- 标题：主副标题。
- 引言：概括时间、事件、重点分析维度。
- 中间：交易过程，前中后每个阶段打开，交易逻辑。
- 可写维度：
  - 并购战略考量
  - 标的筛选
  - 交易结构设计
  - 并购后整合与价值释放
- 结论：经验、启示、教训。

### 6.3 写作风格要求

长期稳定要求：

- 客观。
- 不要主观判断过度。
- 不要特别负面的描述。
- 去除敏感政治、宏观经济等表述。
- 不给公司打广告。
- 专业、克制、有判断力。
- 在学术严谨性与可读性之间平衡。
- 使用流畅、自然、专业的中文。
- 全文基调一致。
- 不要直接把“面向上市公司 CEO”这类思考过程写进正文。
- 不要写“本文 XXX”式引言。

### 6.4 文章质量要求持续升级

用户多次反馈文章太短、模板化、标题差、深度不够。最终形成的核心质量要求：

1. 不要过度结构化、模式化。
2. 结构应根据材料特点灵活调整，文档质量优先于格式统一。
3. 模型应先生成“文章主线/叙事重心”，再由主线决定章节结构。
4. 文章要有深度，除交易复盘外，还应包含产业判断、交易结构分析、财务影响、并购方法论意义等。
5. 标题需准确概括文章主旨，突出核心交易逻辑或分析重点，兼顾专业性与吸引力，不要平淡、空泛或标题党。
6. 全文字数控制在 3500–4000 字，如为逻辑完整可适当超过。
7. 结语/启示必须紧扣本案例，不能泛泛而谈，例如不要写“并购不是终点，整合才是开始”这种空话。
8. 各部分分析不能笼统、浮于表面，必须紧扣本案例实际情况，有依据、有层次、有判断。

### 6.5 文章硬性内容要求

多次迭代后，硬性要求包括：

- 必须说明具体并购时间。
- 必须说明交易对价金额或估值等关键数据。
- 必须有财务数据、交易数据。
- 必须介绍并购方与并购标的。
- 必须说明并购方为什么愿意买这个标的。
- 必须说明被并购方/卖方为什么愿意卖或接受该安排。
- 主副标题必须包含交易双方名称或简称。
- 文章标题整体最好不超过 30 字，但后续更强调标题准确与信息量。
- 文章不固定 5 章，可为 4–7 章，结构根据案例调整。
- 最后一章固定为“结语：副标题”形式，但章节数字应随顺序变化，如“五、结语：...”或“六、结语：...”，不能固定永远是“五”。

### 6.6 选题硬性规则

后续加入：

- 优先写 2025–2026 年已完成且并购成功案例。
- 不在这个时间范围内的，必须是十大分类内比较典型、规模大或明星案例，否则暂时不要。
- `腾讯音乐/喜马拉雅/TME/Ximalaya` 已被排除，用户明确要求不要再写腾讯音乐和喜马拉雅案例。
- 未披露标的/标的公司/某标的/目标方不明等模糊案例不得入选。
- 必须有明确并购方和明确并购标的。

相关修复：

- `case_selection.py` 新增 `VAGUE_PARTY_TERMS`：
  - 未披露
  - 未知
  - 不详
  - 某标的
  - 标的资产
  - 标的公司
  - 相关资产
  - 部分资产
- 新增 `has_explicit_parties()`。
- 选题 prompt 中明确禁止“未披露标的”等案例。
- `rows_to_briefs()` 与 `dedupe_briefs()` 均过滤模糊案例。

### 6.7 Word 格式要求

用户最终给出详细排版规范：

1. 文档网格：
   ```xml
   <w:docGrid w:type="lines" w:linePitch="312"/>
   ```
2. 全篇首行缩进 2 字符，而不是 0.99cm。
3. 段后 0 行，而不是 10 磅。
4. 全文使用一致的全角中文标点。
5. 引号必须为全角中文引号 `“”`，不能用半角 `"` 或 `'`。
6. 中文字符和英文单词或数字之间不要添加空格。
7. 金额、数量等数字使用千分位逗号。
8. 公司首次出现时，应使用括号标注完整名称、简称和股票代码（如上市）。
9. 一级标题：黑体、小三、单倍行距、居中、无首行缩进。
10. 二级标题：仿宋、加粗、四号、单倍行距、左对齐、首行缩进 2 字符。
11. 正文：仿宋、四号、首行缩进 2 字符、段前段后 0。
12. 全角引号要求用 Times New Roman 字体。

### 6.8 公司名称格式问题

用户指出类似错误：

错误：

```text
腾讯音乐（下文简称“腾讯音乐”）娱乐集团
上海喜马拉雅（下文简称“喜马拉雅”）科技有限公司（下称“喜马拉雅”）
```

期望：

```text
腾讯音乐娱乐集团（下称“腾讯音乐”，NYSE：TME）
上海喜马拉雅科技有限公司（下称“喜马拉雅”）
```

后续用户又发现重复：

```text
腾讯音乐娱乐集团（下称“腾讯音乐”，NYSE：TME）（下称“腾讯音乐”，NYSE：TME）...
```

最终决定：不再写腾讯音乐/喜马拉雅案例，并在选题中排除。

### 6.9 三类信息区分要求已取消

用户曾提出严格区分三类信息：

- 官方事实：公司公告、监管文件、交易所文件、反垄断审查公告等。
- 媒体报道或市场传闻：必须写“据媒体报道”“市场认为”。
- 合理推断：必须说明推理依据。

后续用户明确要求：**这个要求取消**。

已修改：

- `mna_case_reports/report_generation.py`
  - commit：`6fd5f6da2cfeccec29383c2ea7dbb904ee532700`
  - 删除三类信息强制区分 prompt。
  - 保留底线：事实、数字、信息必须基于给定资料线索和事实包，不能编造资料外事实。
- `mna_case_reports/article_quality.py`
  - commit：`b5ace724daace0ed0121fe730a295bfb44652d42`
  - 删除媒体/推断相关质量硬拦截。

### 6.10 报告动作与校验问题

用户多次运行 `Weekly M&A case reports` 与 `One-off M&A report preview` 后发现：

- 运行很慢，曾从 20 分钟变为 40 分钟甚至 1.5 小时。
- backfill 有时自动 cancel，看起来像用户取消，但实际可能是 workflow timeout。
- 有时运行完成但没有看到新的 output。
- 有时报错来自旧报告文件的格式校验，而不是本次新生成文件。

为解决：

- Preview workflow 改为只校验本次生成/覆盖的 docx，而不是扫整个 `case_reports_preview` 历史目录。
- Weekly reports workflow 改为只校验本次生成/覆盖的 docx，而不是扫整个 `case_reports` 历史目录。
- 使用 marker 文件：
  ```bash
  touch "$RUNNER_TEMP/preview_start_marker"
  find "$REPORT_OUTPUT_ROOT" -type f -name "*.docx" -newer "$RUNNER_TEMP/preview_start_marker"
  ```
  以及 weekly 对应的：
  ```bash
  touch "$RUNNER_TEMP/weekly_reports_start_marker"
  find "$REPORT_OUTPUT_ROOT" -type f -name "*.docx" -newer "$RUNNER_TEMP/weekly_reports_start_marker"
  ```

### 6.11 DOCX 引号与字体校验问题

用户非常强调半角引号必须消失。

修复过程：

1. `docx_validate.py` 增加对半角 `"` 与 `'` 的硬校验。
2. 若存在半角引号，workflow 失败，不 commit。
3. `docx_writer.py` 将全角中文引号 `“”‘’` 单独设置为 Times New Roman。
4. 一开始 validator 误判：全角引号 run 用 Times New Roman 导致正文非仿宋校验失败。
5. 修复 `docx_validate.py`：允许全角引号 run 使用 Times New Roman，其他中文仍需仿宋/黑体等。
6. 后来章标题中的全角引号被 `docx_writer.py` 在 enforce 阶段重置为非加粗，导致章标题校验失败。
7. 修复：章标题里的全角引号保留 Times New Roman，同时保留加粗。

相关 commit：

- `6a7450e9e4d37d2ad951db3b25cfdf1dcb7987bf`：允许全角引号 Times New Roman。
- `8dfa4807c1d0321157c98798cdd7565e330fe3bf`：保留章标题全角引号加粗。

---

## 7. 重要 bug 与修复记录

### 7.1 DeepSeek JSON malformed

用户贴过报错：DeepSeek 返回 JSON 中有未转义中文引号，例如：

```text
沈国军通过"银泰系"持有约20.93%股权
```

导致：

```text
json.decoder.JSONDecodeError: Expecting ',' delimiter
```

后续在 `deepseek_client.py` 中做过本地 repair 与模型 repair，但仍有失败案例。后续方向：尽量要求模型输出更严格 JSON，或改为分字段生成/Markdown 生成后再结构化，减少长段 JSON 中引号冲突。

### 7.2 `case_selection.py` SyntaxError

用户截图显示 one-off preview 报 `SyntaxError`。原因是普通字符串与条件表达式直接放在括号拼接中，Python 不允许。

修复：把选题 prompt 改成 `prompt_parts` 列表拼接。

commit：`90fcec730f6d49234b822ee1024234d1366395da`

### 7.3 未披露标的案例入选

用户发现生成了“五新隧装收购未披露标的”之类报告，违反明确标的要求。

修复：

- 加入 `VAGUE_PARTY_TERMS`。
- `has_explicit_parties()` 硬过滤。
- 选题 prompt 禁止未披露标的。

commit：`62040c55439e07c74eceb75f3499233ec3b1c2e9`

### 7.4 历史旧报告导致新 run 失败

问题：`docx_validate` 一度扫描整个 `case_reports` 或 `case_reports_preview`，导致历史旧 Word 格式问题使当前 run 失败。

修复：使用 marker 文件，只校验本次生成/覆盖的 `.docx`。

关键 commits：

- Preview 当前 run 校验修复：`d422f17c16f84cf2f30743b8616764b449683537`
- Preview marker 文件修复：`a1ab061c006c1b895c5cb9545bcd1a28422c0363`
- Weekly reports 当前 run 校验修复：`6b4dbfe29907cda1aa9b802c0d7f07c0af89579f`

### 7.5 分类不均衡

用户要求 10 类并购分类尽量均衡。

修复：`choose_balanced()` 调整为：

1. 先按历史 folder 数量从少到多，每类尽量选 1 篇。
2. 再填充剩余名额，对本次已选分类加高惩罚。
3. 日志输出本次分类分布。

commit：`9ecd8292fe604eb0b22df09dab94dfaed6618ddc`

---

## 8. 已知/待确认问题

### 8.1 Excel 原始链接仍需验证

用户最新反馈：“链接依然不对。不是原始链接，打不开”。

最新修复已提交：

- `mna_weekly_tracker/sources_fixed.py`
- commit：`f96fb42a480da636bc0deec0428e7eee16f8807f`

但是否已重新跑出新 Excel 并验证，尚不确定。

接手者应优先执行：

1. 运行 `Weekly M&A cases`。
2. 打开最新 `outputs/并购案例一览_*.xlsx`。
3. 检查 URL 是否为原始文章或公告 URL。
4. 若仍为 Google/Bing/Sogou wrapper，进一步修复 URL 解析。

### 8.2 DeepSeek 可能会把 URL 改坏或选择不佳 URL

Excel 的 `周度并购案例` sheet 的 URL 来源是 DeepSeek 结构化后的 row。虽然候选中的 raw item URL 已尝试解析原始链接，但 DeepSeek 仍可能：

- 输出 wrapper 链接。
- 输出来源首页而非原文。
- 输出多个链接拼接。
- 输出不完整链接。

建议增加后处理：

- 在 `normalize_case()` 或 Excel 写入前，校验 URL。
- 若 URL 非 http(s) 或属于 wrapper 域名，则回到 raw_items 中按 title/source 匹配原始 URL。
- 可增加 `原始候选URL` 与 `结构化URL` 区分。

### 8.3 Sogou 微信原文链接可能天然不可稳定打开

搜狗微信常返回跳转链接或临时链接，可能受 cookie、反爬、时间戳影响。即使解析，微信原文也可能需要特定环境。

建议：

- 对搜狗微信来源增加 `链接可访问性` 字段。
- 若无法稳定解析原文，则保留搜狗搜索结果 URL，同时备注“搜狗微信跳转链接，需人工复核”。
- 不要把搜狗链接伪装成确定可打开原文。

### 8.4 Workflow push 触发可能是临时调试残留

为触发调试，部分 workflow 曾加过：

```yaml
push:
  paths:
    - ".github/workflows/..."
```

稳定后可考虑删除，避免每次编辑 workflow 自动生成报告。

### 8.5 Word 报告质量仍需人工抽检

尽管已加质量检查和格式校验，用户多次反馈标题与内容质量差。后续每次大改后应跑 one-off preview 并人工检查：

- 标题是否具体、有分析重点。
- 字数是否实际在 3500–4000 中文字。
- 是否无半角引号。
- 是否无“上市公司 CEO”等思考过程外露。
- 是否紧扣本案例，而不是通用模板。
- 是否明确交易双方、日期、金额、财务数据。

---

## 9. 重要提交记录清单

以下为聊天中提到过的关键 commit：

| Commit | 内容 |
|---|---|
| `90fcec730f6d49234b822ee1024234d1366395da` | 修复 `case_selection.py` 选题 prompt SyntaxError |
| `62040c55439e07c74eceb75f3499233ec3b1c2e9` | 过滤未披露/模糊标的，要求明确并购方和标的 |
| `9b772e81bec169934109cfd77ebd7dbbd010e48d` | 触发 one-off preview |
| `8f0209791c9e706d6fa010cb77bbc6050863c344` | DOCX 校验增加半角引号检查 |
| `513a480a310c17336fd6f9f388d582a4455649e5` | Reports 曾改为北京时间周一 06:00 |
| `0cda537e86fa8bf25d6659b45cdf03407661dfd9` | Preview DOCX 硬校验 |
| `9ecd8292fe604eb0b22df09dab94dfaed6618ddc` | 改进报告分类均衡 |
| `6a7450e9e4d37d2ad951db3b25cfdf1dcb7987bf` | 允许全角引号 run 使用 Times New Roman |
| `d422f17c16f84cf2f30743b8616764b449683537` | Preview 只校验本次生成/变更 DOCX |
| `a1ab061c006c1b895c5cb9545bcd1a28422c0363` | Preview 用 marker 文件找本次生成 DOCX |
| `6fd5f6da2cfeccec29383c2ea7dbb904ee532700` | 取消三类信息强制区分 prompt |
| `b5ace724daace0ed0121fe730a295bfb44652d42` | 取消媒体/推断相关质量硬拦截 |
| `8dfa4807c1d0321157c98798cdd7565e330fe3bf` | 修复章标题全角引号加粗丢失 |
| `9ac99f6bf505060cfa6608f86fd991b37fcf93f6` | Weekly reports 改为北京时间周五 05:00 |
| `6b4dbfe29907cda1aa9b802c0d7f07c0af89579f` | Weekly reports 只校验本次生成 DOCX |
| `48b6ca17adf9d979e6122dbd803f6e75fd49fd30` | Excel URL 列转为可点击 hyperlink |
| `ef089b05d8165b2eb72ebf10aa4da67cb095f592` | 触发 Excel hyperlink 修复后的 workflow |
| `f96fb42a480da636bc0deec0428e7eee16f8807f` | 尝试解析 Google/Bing/Sogou wrapper URL 为原始链接 |

---

## 10. 用户偏好与沟通注意事项

用户非常重视：

1. 不要偷懒。
2. 不要只改表面格式而忽略内容质量。
3. 出错要明确说明原因，不要沉默或卡住。
4. 如果思考停止或上下文卡住，至少说明问题在哪里。
5. 每次修复后要明确说明：
   - 修了什么文件。
   - commit 是什么。
   - 解决的具体问题是什么。
   - 是否已经验证跑通。
6. 对“跑一下”类请求，应尽量真正触发 GitHub Action，而不是只说可以手动跑。
7. 对历史问题，用户希望保留架构文档/交接文档，便于其他 AI 接手。

---

## 11. 推荐下一步动作

### 11.1 立即动作：验证 Excel 原始链接

1. 触发 `Weekly M&A cases`。
2. 等待跑完并 commit 新 Excel。
3. 打开最新 `outputs/并购案例一览_*.xlsx`。
4. 检查 URL：
   - 是否可点击。
   - 是否原始链接。
   - 是否能打开。
5. 若仍有 wrapper URL，修复 `resolve_original_url()` 或增加后处理校验。

### 11.2 为 Excel 增加 URL 质量校验

建议新增脚本：`mna_weekly_tracker/validate_excel_urls.py`

功能：

- 读取最新 Excel。
- 检查 URL 列是否为 http(s)。
- 标记 wrapper 域名。
- 可选发 HEAD/GET 检测状态码。
- 输出 JSON manifest。
- workflow 中如 wrapper 比例超过阈值则失败或 warning。

### 11.3 报告生成继续稳定化

1. 清理 workflow 临时 `push` 触发。
2. 保留 one-off preview 用于质量抽检。
3. 对文章字数与半角引号继续硬校验。
4. 对“明确并购双方、交易金额、交易日期、财务数据”继续硬校验。
5. 每次 prompt 大改后，先只生成 1 篇 preview 给用户验收。

### 11.4 维护架构文档

用户明确希望“随时 keep 一个架构文档 md”。建议后续任何较大改动同步更新：

- `docs/mna_case_reports_architecture.md`
- `docs/kc_m_a_handoff_summary.md`
- 本文件或新的日期版 handoff。

---

## 12. 当前最后状态摘要

截至本文件生成时：

- Excel URL clickable 已修。
- Excel wrapper URL 解析已修，但尚未确认新 Excel 是否完全满足“原始链接、可打开”。
- Weekly M&A cases 定时：北京时间每周五 05:00。
- Weekly M&A case reports 定时：北京时间每周五 05:00。
- Reports 选题已过滤未披露标的/模糊目标。
- Reports 已取消“三类信息强制区分”要求。
- Reports DOCX 校验已支持：
  - 半角引号硬失败。
  - 全角引号用 Times New Roman。
  - 标题/章标题/正文格式硬校验。
  - 只校验本次生成 DOCX，避免历史旧文件拖累。
- 用户当前最关心的问题：**Excel 里的链接仍不是原始链接、打不开，需要继续修并重跑覆盖旧 Excel。**
