"""Score the calibration dataset under several weight vectors.

    python scripts/calibrate.py

Parses each fixture with the real parser and scores it with the real engine, so
the numbers reflect the shipped pipeline rather than a reimplementation. Writes
`assets/readme/calibration.json` and prints a table.

The question it answers is narrow and honest: *does the shipped weight vector
rank these resumes in the same order a reviewer did, and does any plausible
alternative do better?* It is not a validation study — the reference tiers are
rubric-assigned, not collected from recruiters.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.intelligence.parser import parse_document
from app.intelligence.scoring.calibration import build_sample, evaluate
from app.intelligence.scoring.engine import score_resume
from app.schemas.resume import ExtractionResult

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "scripts" / "calibration_dataset.json"
OUTPUT = ROOT / "assets" / "readme" / "calibration.json"


def load_samples():
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    samples = []
    for entry in payload["samples"]:
        extraction = ExtractionResult(
            text=entry["text"],
            page_count=1,
            method="text_layer",
            confidence=0.95,
            ocr_used=False,
            warnings=[],
        )
        structure = parse_document(extraction)
        bundle = score_resume(structure, extraction_confidence=0.95)
        samples.append(
            build_sample(
                name=entry["name"],
                tier=entry["tier"],
                structure=structure,
                category_scores={key: component.value for key, component in bundle.bundle.components.items()},
            )
        )
    return payload, samples


def main() -> None:
    payload, samples = load_samples()
    results = evaluate(samples)

    print(f"{len(samples)} fixtures, tiers {min(s.tier for s in samples)}–{max(s.tier for s in samples)}\n")
    print(f"{'candidate':22} {'spearman':>9} {'pairwise':>9} {'spread':>8}  weights")
    for row in results:
        weights = ",".join(f"{key[:4]}={value}" for key, value in row["weights"].items())
        print(
            f"{row['name']:22} {row['spearman']:>9.3f} {row['pairwise_accuracy']:>9.3f} "
            f"{row['tier_spread']:>8.1f}  {weights}"
        )

    shipped = results[0]
    best = max(results, key=lambda row: (row["spearman"], row["pairwise_accuracy"]))
    print()
    print(f"shipped vector: spearman {shipped['spearman']:.3f}, pairwise {shipped['pairwise_accuracy']:.3f}")
    if best["name"] == shipped["name"]:
        print("verdict: the shipped vector is not beaten by any alternative tested.")
    else:
        print(
            f"verdict: '{best['name']}' ranks better on this dataset "
            f"(spearman {best['spearman']:.3f}). Changing weights needs a larger, "
            "independently ranked dataset before it is defensible."
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "dataset": str(DATASET.name),
                "note": payload["note"],
                "samples": len(samples),
                "results": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
