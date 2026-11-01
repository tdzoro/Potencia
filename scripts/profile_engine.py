"""Profile the deterministic engine: cost per stage and how it scales.

    cd backend && ./.venv/bin/python ../scripts/profile_engine.py

Answers three questions with numbers rather than adjectives:

1. **Where does the time go?** Cold start versus warm steady state, and the
   cumulative cost of each pipeline stage.
2. **Does it scale linearly?** The same document tripled and octupled in length,
   reporting milliseconds per kilobyte. A regex or nested loop that is
   accidentally quadratic shows up here and nowhere else.
3. **What would be worth optimising?** `cProfile`'s top functions by self time,
   so the fix targets the code that actually burns cycles.

Writes `assets/readme/engine_profile.json`; prints a table.
"""

from __future__ import annotations

import cProfile
import io
import json
import pstats
import statistics
import sys
import time
from pathlib import Path

from app.intelligence.matching.engine import match_resume
from app.intelligence.matching.requirements import extract_requirements
from app.intelligence.parser import parse_document
from app.intelligence.recommendations.rules import generate as generate_recommendations
from app.intelligence.scoring.engine import score_resume
from app.intelligence.taxonomy import all_canonical_names
from app.schemas.resume import ExtractionResult

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "scripts" / "calibration_dataset.json"
OUTPUT = ROOT / "assets" / "readme" / "engine_profile.json"

WARM_RUNS = 200
SCALE_RUNS = 60


def _extraction(text: str) -> ExtractionResult:
    return ExtractionResult(
        text=text,
        page_count=1,
        method="text_layer",
        confidence=0.95,
        ocr_used=False,
        warnings=[],
    )


def _percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "p50": round(statistics.median(ordered), 3),
        "p95": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 3),
        "p99": round(ordered[max(0, int(len(ordered) * 0.99) - 1)], 3),
        "max": round(ordered[-1], 3),
        "mean": round(statistics.fmean(ordered), 3),
    }


def _time(fn, runs: int) -> list[float]:
    samples: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def _pipeline(text: str) -> None:
    structure = parse_document(_extraction(text))
    score_resume(structure, extraction_confidence=0.95)


_SKILL_POOL = all_canonical_names()


def _requirements(count: int):
    """A job description asking for `count` named skills, in the shape the
    extractor already understands."""
    skills = _SKILL_POOL[:count]
    description = (
        "Senior Engineer\nRequirements:\n"
        f"We need 5+ years of experience with {', '.join(skills)}.\n"
        "Bachelor's degree in Computer Science required.\n"
        "Responsibilities:\nOwn the platform service and mentor engineers.\n"
    )
    return extract_requirements(description)


def _full(text: str, requirement_count: int = 12) -> None:
    """Every deterministic stage the product runs for one resume."""
    structure = parse_document(_extraction(text))
    result = score_resume(structure, extraction_confidence=0.95)
    match_resume(structure, _requirements(requirement_count))
    generate_recommendations(result.findings, structure)


def main() -> None:
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    samples = payload["samples"]
    corpus = "\n\n".join(sample["text"] for sample in samples)
    sample_text = samples[0]["text"]

    # --- cold start: the first call pays for regex tables and imports --------
    started = time.perf_counter()
    cold_parse = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    structure = parse_document(_extraction(sample_text))
    cold_parse = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    score_resume(structure, extraction_confidence=0.95)
    cold_score = (time.perf_counter() - started) * 1000

    # --- warm steady state --------------------------------------------------
    parse_samples = _time(lambda: parse_document(_extraction(sample_text)), WARM_RUNS)
    score_samples = _time(lambda: score_resume(structure, extraction_confidence=0.95), WARM_RUNS)
    pipeline_samples = _time(lambda: _pipeline(sample_text), WARM_RUNS)

    requirements = _requirements(12)
    match_samples = _time(lambda: match_resume(structure, requirements), WARM_RUNS)
    scored = score_resume(structure, extraction_confidence=0.95)
    recommendation_samples = _time(
        lambda: generate_recommendations(scored.findings, structure), WARM_RUNS
    )
    full_samples = _time(lambda: _full(sample_text), WARM_RUNS)

    # Matching scales with the number of requirements *and* the document. A
    # per-skill rebuild of the resume context makes that product quadratic; this
    # sweep is what catches it.
    match_scaling: list[dict[str, float]] = []
    match_baseline = _percentiles(_time(lambda: match_resume(structure, _requirements(5)), SCALE_RUNS))["p50"]
    for count in (5, 10, 20, 40):
        measured = _percentiles(_time(lambda: match_resume(structure, _requirements(count)), SCALE_RUNS))["p50"]
        match_scaling.append(
            {
                "requirements": count,
                "p50_ms": measured,
                "ms_per_requirement": round(measured / count, 4),
                "relative_to_5": round(measured / match_baseline, 2),
            }
        )

    # --- scaling: is the cost linear in document length? --------------------
    scaling: list[dict[str, float]] = []
    baseline = _percentiles(_time(lambda: _pipeline(sample_text), SCALE_RUNS))["p50"]
    for factor in (1, 2, 4, 8):
        text = "\n\n".join([sample_text] * factor)
        measured = _percentiles(_time(lambda: _pipeline(text), SCALE_RUNS))["p50"]
        kilobytes = len(text.encode("utf-8")) / 1024
        scaling.append(
            {
                "factor": factor,
                "kilobytes": round(kilobytes, 1),
                "p50_ms": measured,
                "ms_per_kb": round(measured / kilobytes, 3),
                "relative_to_1x": round(measured / baseline, 2),
            }
        )

    # --- where the time goes ------------------------------------------------
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(20):
        _full(corpus)
    profiler.disable()
    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer)
    stats.sort_stats("tottime").print_stats(18)
    top = [
        {
            "function": f"{key[0].split('/')[-1]}:{key[1]} ({key[2]})",
            "self_ms": round(entry[2] * 1000 / 20, 3),
            "cumulative_ms": round(entry[3] * 1000 / 20, 3),
            "calls": entry[1],
        }
        for key, entry in stats.stats.items()
        if entry[2] > 0
    ]
    top.sort(key=lambda row: row["self_ms"], reverse=True)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version.split()[0],
        "corpus": {
            "documents": len(samples),
            "kilobytes": round(len(corpus.encode("utf-8")) / 1024, 1),
            "runs": WARM_RUNS,
        },
        "cold_start_ms": {"parse": round(cold_parse, 3), "score": round(cold_score, 3)},
        "warm_ms": {
            "parse": _percentiles(parse_samples),
            "score": _percentiles(score_samples),
            "pipeline": _percentiles(pipeline_samples),
            "match": _percentiles(match_samples),
            "recommendations": _percentiles(recommendation_samples),
            "full": _percentiles(full_samples),
        },
        "scaling": scaling,
        "match_scaling": match_scaling,
        "top_functions": top[:12],
        "note": (
            "Single process, single thread, no database and no network: this is the "
            "engine's own cost. Wall-clock figures on a laptop are indicative, not a "
            "capacity plan; the scaling ratios are the part that transfers."
        ),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"{len(samples)} documents, {report['corpus']['kilobytes']} KB, {WARM_RUNS} warm runs\n")
    print(f"{'stage':10} {'p50':>8} {'p95':>8} {'p99':>8} {'max':>8}   ms")
    for stage, values in report["warm_ms"].items():
        print(
            f"{stage:10} {values['p50']:>8.2f} {values['p95']:>8.2f} "
            f"{values['p99']:>8.2f} {values['max']:>8.2f}"
        )
    print(f"\ncold start: parse {report['cold_start_ms']['parse']:.2f} ms, "
          f"score {report['cold_start_ms']['score']:.2f} ms")
    print(f"\n{'size':>5} {'KB':>7} {'p50 ms':>8} {'ms/KB':>8} {'vs 1x':>7}")
    for row in scaling:
        print(
            f"{row['factor']:>5}x {row['kilobytes']:>7.1f} {row['p50_ms']:>8.2f} "
            f"{row['ms_per_kb']:>8.3f} {row['relative_to_1x']:>7.2f}"
        )
    print(f"\n{'skills':>7} {'p50 ms':>8} {'ms/skill':>9} {'vs 5x':>7}")
    for row in match_scaling:
        print(
            f"{row['requirements']:>7} {row['p50_ms']:>8.2f} "
            f"{row['ms_per_requirement']:>9.4f} {row['relative_to_5']:>7.2f}"
        )

    print("\ntop functions by self time (ms per full run):")
    for row in top[:8]:
        print(f"  {row['self_ms']:8.3f}  {row['function']}")
    print(f"\nwrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
