from __future__ import annotations

REPORT_TITLE = "加密货币观察"
MAIN_SECTION_ORDER = ("政策风向", "行业前沿", "市场动态", "意见领袖")
SECTION_ORDER = MAIN_SECTION_ORDER
SECTION_COUNTS = {"政策风向": 3, "行业前沿": 2, "市场动态": 2, "意见领袖": 2}
TOTAL_ITEMS = sum(SECTION_COUNTS.values())
MAX_NEWS_AGE_DAYS = 7
RESEARCH_LOOKBACK_DAYS = 62
RESEARCH_REPORT_TITLE = "专题研究"
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

RESEARCH_ORGANIZATION_SITES = {
    "PwC": "pwc.com",
    "KPMG": "kpmg.com",
    "BCG": "bcg.com",
    "PitchBook": "pitchbook.com",
    "McKinsey": "mckinsey.com",
    "BIS": "bis.org",
    "Deloitte": "deloitte.com",
    "EY": "ey.com",
    "Citi": "citigroup.com",
    "JPMorgan": "jpmorgan.com",
    "Cointelegraph Research": "cointelegraph.com",
    "River Research": "river.com",
    "Grayscale Research": "grayscale.com",
    "Kaiko Research": "kaiko.com",
    "Coinbase Institutional Research": "coinbase.com",
    "Chainalysis Reports": "chainalysis.com",
    "SSRN Cryptocurrency": "ssrn.com",
    "Crypto.com Research": "crypto.com",
    "FATF": "fatf-gafi.org",
    "Messari Research": "messari.io",
    "Glassnode Insights": "glassnode.com",
    "Amberdata": "amberdata.io",
    "CoinDesk Data": "coindesk.com",
    "The Block Research": "theblock.co",
    "TRM Labs": "trmlabs.com",
    "Ripple": "ripple.com",
    "MiCA Crypto Alliance": "micacryptoalliance.com",
    "Foresight Ventures": "foresightventures.com",
    "Paradigm": "paradigm.xyz",
    "CoinGecko Reports": "coingecko.com",
    "Galaxy Research": "galaxy.com",
    "CoinShares": "coinshares.com",
    "Fireblocks": "fireblocks.com",
    "a16z crypto": "a16zcrypto.com",
}

RESEARCH_SOURCE_URLS = {
    "Cointelegraph Research": "https://cointelegraph.com/research",
    "Cointelegraph Research Reports": "https://cointelegraph.com/tags/research-reports",
    "River Research": "https://river.com/research",
    "Grayscale Research": "https://research.grayscale.com/",
    "Kaiko Research": "https://research.kaiko.com/reports",
    "Coinbase Institutional Research": "https://www.coinbase.com/institutional/research-insights",
    "Chainalysis Reports": "https://www.chainalysis.com/reports/",
    "SSRN Cryptocurrency": "https://www.ssrn.com/index.cfm/en/cryptocurrency/",
    "Crypto.com Research": "https://crypto.com/en/research",
    "FATF Publications": "https://www.fatf-gafi.org/en/publications.html",
    "Messari Research": "https://messari.io/research",
    "Glassnode Partner Reports": "https://insights.glassnode.com/tag/partner-reports/",
    "Amberdata Blog": "https://blog.amberdata.io/",
    "CoinDesk Data Reports": "https://data.coindesk.com/reports",
    "The Block Research": "https://www.theblock.co/research",
    "TRM Labs Resources": "https://www.trmlabs.com/resources",
    "Ripple Content Library": "https://ripple.com/content-library/",
    "MiCA Crypto Alliance Reports": "https://www.micacryptoalliance.com/reports",
    "Foresight Ventures Research": "https://www.foresightventures.com/research",
    "Paradigm Writing": "https://www.paradigm.xyz/writing",
    "Gate Learn Research": "https://www.gate.io/learn/category/research?page=1",
    "PitchBook": "https://pitchbook.com/",
    "CoinGecko Reports": "https://www.coingecko.com/en/publications/reports",
    "PwC Crypto Services": "https://www.pwc.com/gx/en/industries/financial-services/crypto-services.html",
    "Galaxy Research": "https://www.galaxy.com/insights/research",
    "Citi Insights": "https://www.citigroup.com/global/insights/all",
    "CoinShares Insights": "https://coinshares.com/corp/insights/",
    "Fireblocks Resources": "https://www.fireblocks.com/resources",
    "a16z crypto research": "https://a16zcrypto.com/posts/focus-areas/research/",
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
}
