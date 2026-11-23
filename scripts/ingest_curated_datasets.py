"""
DataPulse Curated Public Dataset Library Ingestion CLI.

Usage examples:
  # Dry-run license & metadata eligibility audit across all 171 manifest entries (no network writes)
  python scripts/ingest_curated_datasets.py --dry-run

  # Download, validate, and save one dataset locally (no R2 required)
  python scripts/ingest_curated_datasets.py --local --limit 1 --report-out curated_local_report.json

  # Ingest a batch to Cloudflare R2 (optional)
  python scripts/ingest_curated_datasets.py --upload-r2 --limit 10 --report-out curated_ingestion_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import init_db
from app.services.curated_ingestion import run_manifest_ingestion
from app.services.r2_storage import R2StorageClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest license-verified curated datasets into Cloudflare R2 and DB.")
    parser.add_argument("--manifest", default="data/curated_manifest.json", help="Path to curated manifest JSON.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate eligibility without downloading or uploading.")
    mode.add_argument("--local", action="store_true", help="Download, validate, and save CSV files under data/curated/ without R2.")
    mode.add_argument("--upload-r2", action="store_true", help="Upload validated compressed CSVs to Cloudflare R2.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of entries to process.")
    parser.add_argument("--dataset-id", action="append", default=None, help="Specific dataset_id(s) to ingest.")
    parser.add_argument("--report-out", default=None, help="Optional JSON path to write full ingestion report.")
    args = parser.parse_args()

    # No mode selected means safe dry-run, preserving the original CLI default.
    local_mode = bool(args.local)
    r2_mode = bool(args.upload_r2)
    dry_run = bool(args.dry_run or not (local_mode or r2_mode))

    if r2_mode:
        r2 = R2StorageClient()
        if not r2.is_configured:
            print("ERROR: --upload-r2 requested, but R2_ENDPOINT_URL / R2_BUCKET_NAME / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY are not configured.")
            return 2

    if local_mode or r2_mode:
        init_db()

    report = run_manifest_ingestion(
        manifest_path=args.manifest,
        dataset_ids=args.dataset_id,
        limit=args.limit,
        dry_run=dry_run,
        upload_to_r2=r2_mode and not dry_run,
    )

    summary = {
        "manifest_version": report["manifest_version"],
        "dry_run": report["dry_run"],
        "upload_to_r2": report["upload_to_r2"],
        "total_processed": report["total_processed"],
        "success_count": report["success_count"],
        "failure_count": report["failure_count"],
        "excluded_count": report["excluded_count"],
    }
    print(json.dumps(summary, indent=2))

    if args.report_out:
        Path(args.report_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote detailed report to {args.report_out}")

    return 0 if report["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

