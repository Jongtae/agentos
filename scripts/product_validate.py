"""Run the Personal AgentOS product-validation gate."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from product_validation import ProductValidator, markdown


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", action="store_true", help="Run the full automated contract suite.")
    parser.add_argument("--homebrew", action="store_true", help="Run installed Homebrew acceptance if available.")
    parser.add_argument("--compose", action="store_true", help="Validate Docker Compose configuration if Docker is available.")
    parser.add_argument("--live-model", action="store_true", help="Use the existing local model credential for live acceptance.")
    parser.add_argument("--live-telegram", action="store_true", help="Record that the paired-account Telegram check is required.")
    parser.add_argument("--output", type=Path, help="Write the redacted JSON report to this path.")
    parser.add_argument("--markdown", type=Path, help="Write the human-readable report to this path.")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    validator = ProductValidator(root)
    validator.documentation(); validator.source_contracts(); validator.vision_gaps()
    validator.local_checks(args.unit, args.homebrew, args.compose)
    validator.live_checks(args.live_model, args.live_telegram)
    report = validator.report()
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(markdown(report), encoding="utf-8")
    print(encoded)
    return 1 if report["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
