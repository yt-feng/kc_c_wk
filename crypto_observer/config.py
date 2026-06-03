from __future__ import annotations

REPORT_TITLE = "加密货币观察"
SECTION_ORDER = ("政策风向", "行业前沿", "市场动态", "意见领袖", "专题研究")
SECTION_COUNTS = {"政策风向": 3, "行业前沿": 2, "市场动态": 2, "意见领袖": 2, "专题研究": 1}
TOTAL_ITEMS = sum(SECTION_COUNTS.values())
MAX_NEWS_AGE_DAYS = 7
US_TERMS = ("US", "U.S.", "United States", "America", "American", "SEC", "CFTC", "Treasury", "Federal Reserve", "Fed", "Congress", "White House", "IRS", "FinCEN")
HK_TERMS = ("Hong Kong", "HK", "SFC", "Hong Kong SFC", "HKMA", "HKSAR", "香港")
ESTABLISHED_POLICY_TERMS = ("approved", "adopted", "enacted", "signed", "final", "effective", "issued", "guidance", "rule", "law", "licence", "license", "framework", "circular", "statement")
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
    "Federal Reserve": "site:federalreserve.gov crypto stablecoin digital asset",
    "US Treasury": "site:treasury.gov crypto digital asset stablecoin",
    "Hong Kong SFC": "site:sfc.hk crypto virtual asset",
    "Hong Kong HKMA": "site:hkma.gov.hk crypto stablecoin tokenisation",
    "Hong Kong Government": "site:info.gov.hk virtual asset crypto",
    "BIS": "site:bis.org crypto stablecoin",
    "ESMA": "site:esma.europa.eu crypto MiCA",
    "Messari": "site:messari.io crypto report",
    "Glassnode": "site:glassnode.com bitcoin market report",
}

FRONTIER_QUERIES = (
    "blockchain protocol upgrade DeFi Layer 2 Ethereum",
    "crypto infrastructure launch interoperability tokenization",
)

SECTION_QUERIES = {
    "政策风向": (
        "US crypto regulation SEC CFTC Treasury stablecoin final rule guidance",
        "Hong Kong virtual asset crypto SFC HKMA stablecoin regulation",
        "crypto regulation adopted enacted final guidance digital asset",
        "MiCA crypto regulation stablecoin CASP final guidance",
    ),
    "行业前沿": FRONTIER_QUERIES,
    "市场动态": FRONTIER_QUERIES,
    "意见领袖": ("crypto opinion CEO investor analyst says bitcoin", "cryptocurrency interview founder economist bitcoin"),
    "专题研究": ("crypto research report bitcoin market stablecoin", "digital assets report blockchain research"),
}
