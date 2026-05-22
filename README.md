# kc_c_wk：《加密货币观察》周刊自动生成

本仓库用于每周自动生成一版中文 Word 周刊《加密货币观察》。实现参考 `yt-feng/kc-m-a` 的思路：配置化信息源、自动采集候选资讯、LLM 编译结构化内容、输出前执行事实核验，并由 GitHub Actions 定时提交产物。

## 栏目与数量

脚本按“加密货币观察AI模版”的栏目设置生成：

- 【政策风向】3 条，且至少 1 条必须是美国相关资讯
- 【行业前沿】2 条
- 【市场动态】2 条
- 【意见领袖】2 条
- 【专题研究】1 篇

所有候选必须来自最近 3 天内发生或发布的事件；输出前会检查来源发布时间和事件日期是否落在统计窗口内。

## 信息源原则

信息源配置位于：

```text
crypto_observer/config.py
```

来源池来自上传的 `加密货币观察_网站.xlsx`，并按需求排除了中文网站和中文页面。代码会优先使用加密垂类和研究源，例如 CoinDesk、Decrypt、The Block、Cointelegraph、CryptoSlate、Blockworks、The Defiant、Messari、Glassnode、CoinGecko 等；同时使用以下发现源补充检索：

- Google News RSS
- Bing News RSS
- GDELT DOC API

采集与事实核验层都会过滤中文域名、中文路径和明显中文标题/摘要。

## 输出

每次成功运行会生成：

```text
reports/YYYY/加密货币观察_YYYYMMDD.docx
reports/YYYY/_manifests/加密货币观察_YYYYMMDD.json
```

Word 报告包含目录、五个栏目正文、信息来源、发布时间和自动事实核验摘要。JSON manifest 保留候选数量、最终入选条目、URL、事实核验结果和采集警告，便于复核。

## 自动运行时间

GitHub Actions 配置为：**北京时间每周三 14:00** 自动运行一次，预留 2 小时用于采集、LLM 编译、fact check 和提交，确保北京时间周三 16:00 前产出。

GitHub Actions cron 使用 UTC，因此 workflow 中配置的是：

```yaml
- cron: "0 6 * * 3"
```

即 UTC 周三 06:00 = 北京时间周三 14:00。

## Secret 配置

需要在仓库 Settings → Secrets and variables → Actions 中配置：

```text
DEEPSEEK_API_KEY
```

可选：

```text
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

没有 `DEEPSEEK_API_KEY` 时，脚本会使用保守的标题/摘要 fallback 生成草稿；在默认严格模式下，如果栏目数量、美国政策条目或日期等硬性要求不满足，会拒绝写入 DOCX，只保留 manifest 供排查。

## 手动运行

```bash
pip install -r requirements.txt
export DEEPSEEK_API_KEY="your_api_key"
python -m crypto_observer.main --days 3 --output-root reports --strict
```

调试时可以关闭严格模式生成草稿：

```bash
python -m crypto_observer.main --days 3 --output-root reports --no-strict --verbose
```

## 输出前事实核验

`crypto_observer/factcheck.py` 会在写 Word 前执行以下检查：

- 五个栏目数量是否满足模板要求
- 政策风向是否至少包含一条美国相关资讯
- 来源发布时间与事件日期是否在最近 3 天窗口内
- 是否来自中文网站、中文路径或中文标题/摘要
- 来源域名是否足够分散，同一域名是否过度集中
- URL 格式是否有效；可选开启 URL 可访问性检查

默认 `--strict` 开启；如果存在硬性错误，GitHub Action 会失败，避免生成不准确或编造内容。
