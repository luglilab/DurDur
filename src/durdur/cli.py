from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import run_qc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="durdur", description="Unified QC tool inspired by flowAI, flowClean, and PeacoQC.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run QC on a file")
    run_parser.add_argument("input", help="Path to .fcs, .csv, .tsv, or .txt input data")
    run_parser.add_argument("--engine", default="combined", choices=["flowai", "flowclean", "peacoqc", "combined"])
    run_parser.add_argument("--combination-strategy", default="majority", choices=["majority", "intersection", "union"])
    run_parser.add_argument("--report-dir", help="Optional directory where HTML and PNG reports will be generated")
    run_parser.add_argument("--preprocess-margins", action="store_true")
    run_parser.add_argument("--preprocess-doublets", action="store_true")
    run_parser.add_argument("--summary-json", help="Optional path to write the summary JSON")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        result = run_qc(
            args.input,
            engine=args.engine,
            combination_strategy=args.combination_strategy,
            report_dir=args.report_dir,
            preprocess_margins=args.preprocess_margins,
            preprocess_doublets=args.preprocess_doublets,
        )
        summary = result.summary()
        print(json.dumps(summary, indent=2))
        if args.summary_json:
            Path(args.summary_json).write_text(json.dumps(summary, indent=2) + "\n")
        return 0

    return 1
