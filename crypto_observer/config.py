from __future__ import annotations

REPORT_TITLE = "加密货币观察"
MAIN_SECTION_ORDER = ("政策风向", "行业前沿", "市场动态", "意见领袖")
SECTION_ORDER = MAIN_SECTION_ORDER
SECTION_COUNTS = {"政策风向": 3, "行业前沿": 2, "市场动态": 2, "意见领袖": 2}
TOTAL_ITEMS = sum(SECTION_COUNTS.values())
MAX_NEWS_AGE_DAYS = 7
RESEARCH_LOOKBACK_DAYS = 62
RESEARCH_REPORT_TITLE = "专题研究"

US_TERMS = (
    "US", "U.S.", "United States", "America", "American", "SEC", "CFTC", "Treasury", "Federal Reserve", "Fed",
    "Congress", "Senate", "House", "White House", "IRS", "FinCEN", "OCC", "FDIC"
)
HK_TERMS = ("Hong Kong", "HK", "SFC", "Hong Kong SFC", "HKMA", "HKSAR", "FSTB", "香港")
ESTABLISHED_POLICY_TERMS = (
    "approved", "adopted", "enacted", "signed", "final", "effective", "issued", "guidance", "rule", "law",
    "licence", "license", "framework", "circular", "statement", "consultation", "bill", "act", "regulation"
)
EXCLUDED_DOMAINS = (
    "8btc.com", "panewslab.com", "blockbeats.info", "odaily.news", "chaincatcher.com", "jinse.cn",
    "qq.com", "sina.com.cn", "163.com", "sohu.com", "baidu.com", "thepaper.cn", "xinhua", "people.cn"
)
USER_AGENT = "Mozilla/5.0 CryptoObserverBot/1.0 (+https://github.com/yt-feng/kc_c_wk)"

# High-quality discovery targets. These are used only for finding candidates; final output must use the original publisher URL.
TRACKED_SITES = {
    "CoinDesk": "site:coindesk.com (crypto OR bitcoin OR ethereum OR stablecoin OR tokenization OR digital assets)",
    "The Block": "site:theblock.co (crypto OR bitcoin OR ethereum OR stablecoin OR tokenization OR digital assets)",
    "Decrypt": "site:decrypt.co (crypto OR bitcoin OR ethereum OR stablecoin OR tokenization OR digital assets)",
    "Cointelegraph": "site:cointelegraph.com (crypto OR bitcoin OR ethereum OR stablecoin OR tokenization OR digital assets)",
    "Blockworks": "site:blockworks.co (crypto OR bitcoin OR ethereum OR stablecoin OR tokenization OR digital assets)",
    "CryptoSlate": "site:cryptoslate.com (crypto OR bitcoin OR ethereum OR stablecoin OR tokenization OR digital assets)",
    "The Defiant": "site:thedefiant.io (DeFi OR Ethereum OR protocol OR tokenization OR stablecoin)",
    "Ledger Insights": "site:ledgerinsights.com (tokenization OR stablecoin OR digital assets OR blockchain)",
    "FinanceFeeds": "site:financefeeds.com (crypto OR digital assets OR tokenization OR stablecoin)",
    "SEC": "site:sec.gov (crypto OR digital asset OR stablecoin OR tokenized)",
    "CFTC": "site:cftc.gov (crypto OR digital asset OR prediction market OR event contract)",
    "Federal Reserve": "site:federalreserve.gov (crypto OR stablecoin OR digital asset OR tokenization)",
    "US Treasury": "site:treasury.gov (crypto OR digital asset OR stablecoin OR FinCEN OR OFAC)",
    "Hong Kong SFC": "site:sfc.hk (virtual asset OR crypto OR tokenised OR tokenized OR stablecoin)",
    "Hong Kong HKMA": "site:hkma.gov.hk (stablecoin OR tokenisation OR tokenization OR digital asset)",
    "Hong Kong Government": "site:info.gov.hk (virtual asset OR crypto OR stablecoin OR tokenisation)",
    "BIS": "site:bis.org (crypto OR stablecoin OR tokenisation OR tokenization)",
    "ESMA": "site:esma.europa.eu (crypto OR MiCA OR CASP OR stablecoin)",
    "FCA": "site:fca.org.uk (crypto OR tokenisation OR tokenization OR stablecoin)",
    "Bank of England": "site:bankofengland.co.uk (stablecoin OR tokenisation OR tokenization OR digital money)",
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
    "Crypto.com Research": "crypto.com",
    "FATF": "fatf-gafi.org",
    "Messari Research": "messari.io",
    "Glassnode Insights": "glassnode.com",
    "CoinDesk Data": "coindesk.com",
    "The Block Research": "theblock.co",
    "TRM Labs": "trmlabs.com",
    "Ripple": "ripple.com",
    "PitchBook": "pitchbook.com",
    "Galaxy Research": "galaxy.com",
    "CoinShares": "coinshares.com",
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
    "Crypto.com Research": "https://crypto.com/en/research",
    "FATF Publications": "https://www.fatf-gafi.org/en/publications.html",
    "Messari Research": "https://messari.io/research",
    "Glassnode Partner Reports": "https://insights.glassnode.com/tag/partner-reports/",
    "CoinDesk Data Reports": "https://data.coindesk.com/reports",
    "The Block Research": "https://www.theblock.co/research",
    "TRM Labs Resources": "https://www.trmlabs.com/resources",
    "Ripple Content Library": "https://ripple.com/content-library/",
    "PitchBook": "https://pitchbook.com/",
    "CoinGecko Reports": "https://www.coingecko.com/en/publications/reports",
    "PwC Crypto Services": "https://www.pwc.com/gx/en/industries/financial-services/crypto-services.html",
    "Galaxy Research": "https://www.galaxy.com/insights/research",
    "Citi Insights": "https://www.citigroup.com/global/insights/all",
    "CoinShares Insights": "https://coinshares.com/corp/insights/",
    "a16z crypto research": "https://a16zcrypto.com/posts/focus-areas/research/",
}

SECTION_QUERIES = {
    "政策风向": (
        "US crypto regulation SEC CFTC Treasury stablecoin digital asset law guidance",
        "Hong Kong SFC HKMA virtual asset stablecoin tokenised investment product regulation",
        "MiCA ESMA CASP stablecoin crypto regulation guidance",
        "crypto digital assets regulation law approved enacted issued final guidance",
        "Bank of England FCA tokenisation stablecoin consultation digital securities",
    ),
    "行业前沿": (
        "Ethereum Solana Chainlink protocol upgrade mainnet tokenization blockchain infrastructure",
        "DeFi protocol institutional stablecoin lending tokenized assets launch",
        "tokenized treasury blockchain settlement JPMorgan Mastercard Ripple digital assets",
        "cross chain oracle RWA infrastructure wallet staking rollup interoperability crypto",
    ),
    "市场动态": (
        "crypto acquisition funding IPO futures CME stablecoin revenue tokenized securities",
        "digital asset exchange institutional adoption tokenized stock stablecoin payment market",
        "crypto company raises acquires launches futures ETF tokenized fund stablecoin adoption",
        "prediction market Polymarket Kalshi institutional crypto market infrastructure",
    ),
    "意见领袖": (
        "crypto CEO says stablecoin tokenization bitcoin interview digital assets",
        "BIS central bank governor stablecoin tokenization says digital assets",
        "investor analyst CIO says DeFi stablecoin bitcoin crypto market structure",
        "opinion crypto stablecoin tokenization digital assets financial infrastructure",
    ),
}
