from __future__ import annotations

REPORT_TITLE = "加密货币观察"
SECTION_ORDER = ("政策风向", "行业前沿", "市场动态", "意见领袖", "专题研究")
SECTION_COUNTS = {"政策风向": 3, "行业前沿": 2, "市场动态": 2, "意见领袖": 2, "专题研究": 1}
US_TERMS = ("US", "U.S.", "United States", "SEC", "CFTC", "Treasury", "Federal Reserve", "Congress", "White House", "IRS", "FinCEN")
EXCLUDED_DOMAINS = ("8btc.com", "panewslab.com", "blockbeats.info", "odaily.news", "chaincatcher.com", "jinse.cn", "qq.com", "sina.com.cn", "163.com", "sohu.com", "baidu.com")
USER_AGENT = "Mozilla/5.0 CryptoObserverBot"

TRACKED_SITES = {
    "CoinDesk": "site:coindesk.com crypto",
    "Decrypt": "site:decrypt.co crypto",
    "The Block": "site:theblock.co crypto",
    "Cointelegraph": "site:cointelegraph.com crypto",
    "Blockworks": "site:blockworks.co crypto",
    "CryptoSlate": "site:cryptoslate.com crypto",
    "The Defiant": "site:thedefiant.io DeFi crypto",
    "SEC": "site:sec.gov crypto digital asset",
    "CFTC": "site:cftc.gov crypto digital asset",
    "BIS": "site:bis.org crypto stablecoin",
    "ESMA": "site:esma.europa.eu crypto MiCA",
    "Messari": "site:messari.io crypto report",
    "Glassnode": "site:glassnode.com bitcoin market report",
}

SECTION_QUERIES = {
    "政策风向": ("US crypto regulation SEC CFTC Treasury stablecoin", "MiCA crypto regulation stablecoin", "crypto enforcement digital asset"),
    "行业前沿": ("blockchain protocol upgrade DeFi Layer 2 Ethereum", "crypto infrastructure launch interoperability tokenization"),
    "市场动态": ("bitcoin ETF crypto market funding exchange", "crypto market inflows acquisition IPO"),
    "意见领袖": ("crypto opinion CEO investor analyst says bitcoin", "cryptocurrency interview founder economist bitcoin"),
    "专题研究": ("crypto research report bitcoin market stablecoin", "digital assets report blockchain research"),
}
