"""Run the consent-gated 200-resume calibration study.

    python scripts/calibration_study.py --corpus path/to/study.json

The corpus must declare consent and anonymisation, contain at least 200 resumes,
and provide two independent 1–5 ratings per resume. Nothing is fetched or
generated: this script refuses to fabricate a study.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.intelligence.scoring.study import StudyError, run_study

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "assets" / "readme" / "calibration_study.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True, help="JSON study corpus")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--kappa-target", type=float, default=0.7)
    parser.add_argument("--train-fraction", type=float, default=0.5)
    parser.add_argument("--step", type=int, default=10, help="weight grid step")
    args = parser.parse_args()

    try:
        payload = json.loads(args.corpus.read_text(encoding="utf-8"))
        report = run_study(
            payload,
            kappa_target=args.kappa_target,
            train_fraction=args.train_fraction,
            step=args.step,
        )
    except (OSError, json.JSONDecodeError, StudyError) as exc:
        print(f"study refused: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    inter = report["inter_rater"]
    print(
        f"{report['corpus']['samples']} samples | weighted kappa {inter['weighted_kappa']:.3f} "
        f"| raw agreement {inter['raw_agreement']:.3f}"
    )
    print(f"split: {report['split']['train']} train / {report['split']['holdout']} holdout")
    for name, metrics in report["holdout"].items():
        print(
            f"{name:14} rho {metrics['spearman']:.3f}  pairwise {metrics['pairwise_accuracy']:.3f}  "
            f"MAE {metrics['mae_points']:.2f}"
        )
    print(f"\nstatus: {report['status']}\n{report['verdict']}")
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
