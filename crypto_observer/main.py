from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from .config import SECTION_ORDER, TOTAL_ITEMS
from .sources import collect
from .deepseek import compile_report
from .factcheck import check_report, FactCheckResult
from .docx_writer import write_docx

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crypto Observer Weekly Generator")
    parser.add_argument("--days", type=int, default=3, help="Lookback window in days")
    parser.add_argument("--output-root", type=str, default="reports", help="Output folder")
    parser.add_argument("--strict", dest="strict", action="store_true", help="Fail on fact-check errors")
    parser.add_argument("--no-strict", dest="strict", action="store_false", help="Generate draft even if fact-check fails")
    parser.set_defaults(strict=True)
    return parser.parse_args()


def main():
    args = parse_args()
    start, end = None, None
    try:
        raw_items, errors = collect(args.days)
        LOGGER.info("Collected %d candidate items", len(raw_items))
        start = (datetime.now()).replace(microsecond=0)
        report = compile_report(raw_items, start_label=f"最近{args.days}天", end_label=f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")
        fact = check_report(report, start=start, end=datetime.now())
        output_root = Path(args.output_root) / datetime.now().strftime('%Y')
        output_file = output_root / f"加密货币观察_{datetime.now().strftime('%Y%m%d')}.docx"
        write_docx(report, output_file, metadata={"generated_at": datetime.now().strftime('%Y-%m-%d %H:%M'), "period": f"最近{args.days}天", "raw_count": len(raw_items), "factcheck": asdict(fact)})
        manifest_file = output_root / "_manifests" / f"加密货币观察_{datetime.now().strftime('%Y%m%d')}.json"
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        json.dump({"raw_count": len(raw_items), "report": report, "factcheck": asdict(fact), "errors": errors}, open(manifest_file, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        if args.strict and not fact.ok:
            LOGGER.error("Fact check failed, exiting due to strict mode")
            sys.exit(1)
    except Exception as e:
        LOGGER.exception("Failed to generate report: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()