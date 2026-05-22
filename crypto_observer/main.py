from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .deepseek import compile_report
from .docx_writer import write_docx
from .factcheck import check_report
from .sources import collect

LOGGER = logging.getLogger(__name__)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the weekly Crypto Observer report.")
    parser.add_argument("--days", type=int, default=int(os.getenv("CRYPTO_OBSERVER_DAYS", "3")), help="Lookback window in days.")
    parser.add_argument("--output-root", default=os.getenv("CRYPTO_OBSERVER_OUTPUT_ROOT", "reports"), help="Output folder.")
    parser.add_argument("--max-raw-items", type=int, default=int(os.getenv("CRYPTO_OBSERVER_MAX_RAW_ITEMS", "360")), help="Maximum raw candidates to keep.")
    parser.add_argument("--strict", dest="strict", action="store_true", help="Fail when fact-check has hard errors.")
    parser.add_argument("--no-strict", dest="strict", action="store_false", help="Write draft even when fact-check has hard errors.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    parser.set_defaults(strict=(os.getenv("CRYPTO_OBSERVER_STRICT", "1") != "0"))
    return parser.parse_args()


def iso_label(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def main() -> None:
    args = parse_args()
    configure_logging(args.verbose)
    end = datetime.now(BEIJING_TZ).replace(microsecond=0)
    start = end.replace(microsecond=0) - __import__("datetime").timedelta(days=args.days)
    period = f"{iso_label(start)} 至 {iso_label(end)}（北京时间，最近{args.days}天）"

    try:
        raw_items, collection_warnings = collect(args.days, max_items=args.max_raw_items)
        LOGGER.info("Collected %d candidate items", len(raw_items))
        report = compile_report(raw_items, start_label=iso_label(start), end_label=iso_label(end))
        fact = check_report(report, start=start, end=end)

        output_root = Path(args.output_root) / end.strftime("%Y")
        output_file = output_root / f"加密货币观察_{end.strftime('%Y%m%d')}.docx"
        manifest_file = output_root / "_manifests" / f"加密货币观察_{end.strftime('%Y%m%d')}.json"
        manifest_file.parent.mkdir(parents=True, exist_ok=True)

        metadata = {
            "generated_at": iso_label(end),
            "period": period,
            "raw_count": len(raw_items),
            "factcheck": fact.as_dict(),
        }
        write_docx(report, output_file, metadata=metadata)
        manifest = {
            "generated_at": end.isoformat(),
            "period": period,
            "raw_count": len(raw_items),
            "collection_warnings": collection_warnings,
            "report": report,
            "factcheck": fact.as_dict(),
            "outputs": {"docx": str(output_file), "manifest": str(manifest_file)},
        }
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.info("Wrote %s", output_file)
        LOGGER.info("Wrote %s", manifest_file)

        if args.strict and not fact.ok:
            LOGGER.error("Fact check failed in strict mode: %s", "; ".join(fact.errors))
            sys.exit(1)
    except Exception as exc:
        LOGGER.exception("Failed to generate report: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
