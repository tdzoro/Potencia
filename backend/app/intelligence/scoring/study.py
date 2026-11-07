"""Consent-gated calibration study harness.

The eight authored fixtures in `calibration_dataset.json` are regression probes,
not an empirical study. This module defines the stronger protocol: at least 200
anonymised resumes, two independent ordinal ratings each, inter-rater agreement
reported before any engine number, a deterministic train/holdout split, and a
coarse weight search fitted on the training half only.

It never edits the shipped weights. A result that looks better on the holdout is
reported as a candidate for review, not silently adopted.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.intelligence.parser import parse_document
from app.intelligence.scoring.calibration import normalise, spearman, weighted_total
from app.intelligence.scoring.engine import score_resume
from app.schemas.resume import ExtractionResult
from app.schemas.scores import CATEGORY_WEIGHTS

MIN_SAMPLES = 200
KAPPA_TARGET = 0.7
TIERS = (1, 2, 3, 4, 5)
_CATEGORY_KEYS = tuple(CATEGORY_WEIGHTS)


class StudyError(ValueError):
    """The corpus or protocol is not usable for a study."""


@dataclass(frozen=True)
class RatedSample:
    id: str
    text: str
    rater_a: int
    rater_b: int

    @property
    def consensus(self) -> float:
        return (self.rater_a + self.rater_b) / 2


@dataclass(frozen=True)
class ScoredSample:
    sample: RatedSample
    category_scores: dict[str, float]


def validate_corpus(
    payload: Any, *, min_samples: int = MIN_SAMPLES
) -> tuple[list[RatedSample], str]:
    """Validate consent, anonymisation and every rating before scoring anything."""
    if not isinstance(payload, dict):
        raise StudyError("corpus must be a JSON object")

    consent = payload.get("consent")
    if not isinstance(consent, dict):
        raise StudyError("corpus must include a consent object")
    if consent.get("confirmed") is not True:
        raise StudyError("consent.confirmed must be true; do not study resumes without permission")
    if consent.get("anonymised") is not True:
        raise StudyError("consent.anonymised must be true; remove names, emails and phone numbers")
    basis = str(consent.get("basis") or "").strip()
    if len(basis) < 10:
        raise StudyError("consent.basis must describe how consent was obtained")

    entries = payload.get("samples")
    if not isinstance(entries, list):
        raise StudyError("corpus.samples must be a list")
    if len(entries) < min_samples:
        raise StudyError(f"study needs at least {min_samples} samples; found {len(entries)}")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise StudyError(f"samples[{index}] must be an object")
    if len({str(entry.get("id", "")).strip() for entry in entries}) < len(entries):
        raise StudyError("every sample needs a unique non-empty id")

    samples: list[RatedSample] = []
    for index, entry in enumerate(entries):
        sample_id = str(entry.get("id") or "").strip()
        text = str(entry.get("text") or "").strip()
        rater_a = entry.get("rater_a")
        rater_b = entry.get("rater_b")
        if not sample_id:
            raise StudyError(f"samples[{index}].id is required")
        if len(text) < 20:
            raise StudyError(f"samples[{index}] has no usable resume text")
        for label, rating in (("rater_a", rater_a), ("rater_b", rater_b)):
            if isinstance(rating, bool) or not isinstance(rating, int) or rating not in TIERS:
                raise StudyError(f"samples[{index}].{label} must be an integer from 1 to 5")
        samples.append(RatedSample(sample_id, text, rater_a, rater_b))

    return samples, basis


def weighted_kappa(left: Iterable[int], right: Iterable[int]) -> float:
    """Linear-weighted Cohen's kappa for two ordinal ratings on a 1–5 scale."""
    first, second = list(left), list(right)
    if len(first) != len(second) or len(first) < 2:
        raise StudyError("kappa needs two equally sized rating lists with at least two pairs")

    matrix = [[0] * 5 for _ in range(5)]
    for a, b in zip(first, second, strict=True):
        if a not in TIERS or b not in TIERS:
            raise StudyError("ratings must be integers from 1 to 5")
        matrix[a - 1][b - 1] += 1

    total = len(first)

    def weight(a: int, b: int) -> float:
        # Disagreement weight: zero on the diagonal, one at opposite ends.
        return abs(a - b) / 4.0

    observed = sum(weight(a, b) * matrix[a][b] for a in range(5) for b in range(5)) / total
    rows = [sum(row) for row in matrix]
    columns = [sum(matrix[row][column] for row in range(5)) for column in range(5)]
    expected = sum(
        weight(a, b) * rows[a] * columns[b] for a in range(5) for b in range(5)
    ) / (total * total)

    if expected == 0:
        return 1.0
    return round(1.0 - observed / expected, 4)


def raw_agreement(left: Iterable[int], right: Iterable[int]) -> float:
    first, second = list(left), list(right)
    if len(first) != len(second) or not first:
        raise StudyError("agreement needs two equally sized non-empty rating lists")
    return round(sum(a == b for a, b in zip(first, second, strict=True)) / len(first), 4)


def score_samples(samples: list[RatedSample]) -> list[ScoredSample]:
    """Run every corpus entry through the real parser and scorer."""
    scored: list[ScoredSample] = []
    for sample in samples:
        extraction = ExtractionResult(
            text=sample.text,
            page_count=1,
            method="text_layer",
            confidence=1.0,
            ocr_used=False,
            warnings=[],
        )
        try:
            structure = parse_document(extraction)
            result = score_resume(structure, extraction_confidence=1.0)
        except Exception as exc:
            raise StudyError(f"could not score sample {sample.id}: {exc}") from exc
        scored.append(
            ScoredSample(
                sample=sample,
                category_scores={
                    key: component.value for key, component in result.bundle.components.items()
                },
            )
        )
    return scored


def split_samples(
    samples: list[RatedSample], *, fraction: float = 0.5
) -> tuple[list[RatedSample], list[RatedSample]]:
    """Deterministic split: SHA-256 of the id, so the same corpus splits the same way."""
    if not 0 < fraction < 1:
        raise StudyError("train fraction must be between 0 and 1")
    if len(samples) < 2:
        raise StudyError("a split needs at least two samples")

    ordered = sorted(samples, key=lambda sample: hashlib.sha256(sample.id.encode()).hexdigest())
    cut = max(1, min(len(ordered) - 1, round(len(ordered) * fraction)))
    return ordered[:cut], ordered[cut:]


def evaluate_scored(
    samples: list[ScoredSample], weights: Mapping[str, int]
) -> dict[str, float]:
    if not samples:
        raise StudyError("cannot evaluate an empty sample set")

    tiers = [sample.sample.consensus for sample in samples]
    totals = [weighted_total(sample.category_scores, dict(weights)) for sample in samples]

    pairwise_correct = pairwise_total = 0
    for left in range(len(samples)):
        for right in range(left + 1, len(samples)):
            if tiers[left] == tiers[right]:
                continue
            pairwise_total += 1
            if (totals[left] > totals[right]) == (tiers[left] > tiers[right]):
                pairwise_correct += 1

    by_tier: dict[int, list[float]] = {}
    for tier, total in zip(tiers, totals, strict=True):
        by_tier.setdefault(round(tier), []).append(total)
    tier_means = [sum(values) / len(values) for _, values in sorted(by_tier.items())]
    spread = round(tier_means[-1] - tier_means[0], 2) if len(tier_means) >= 2 else 0.0
    mae = sum(abs(total - tier * 20) for tier, total in zip(tiers, totals, strict=True)) / len(tiers)

    return {
        "spearman": spearman(tiers, totals),
        "pairwise_accuracy": round(pairwise_correct / pairwise_total, 4) if pairwise_total else 0.0,
        "mae_points": round(mae, 2),
        "tier_spread": spread,
        "min": round(min(totals), 2),
        "max": round(max(totals), 2),
    }


def weight_vectors(*, step: int = 10, minimum: int = 10) -> Iterable[dict[str, int]]:
    """Coarse simplex of category weights, e.g. six parts in steps of ten."""
    if step <= 0 or minimum <= 0 or minimum % step or 100 % step:
        raise StudyError("step and minimum must divide 100 evenly")
    units = 100 // step
    minimum_units = minimum // step

    def compositions(total: int, parts: int) -> Iterable[tuple[int, ...]]:
        if parts == 1:
            if total >= minimum_units:
                yield (total,)
            return
        for value in range(minimum_units, total - minimum_units * (parts - 1) + 1):
            for rest in compositions(total - value, parts - 1):
                yield (value, *rest)

    for units_vector in compositions(units, len(_CATEGORY_KEYS)):
        yield {key: value * step for key, value in zip(_CATEGORY_KEYS, units_vector, strict=True)}


def _distance(left: Mapping[str, int], right: Mapping[str, int]) -> int:
    return sum(abs(left[key] - right[key]) for key in _CATEGORY_KEYS)


def fit_weights(
    samples: list[ScoredSample], *, step: int = 10, minimum: int = 10
) -> tuple[dict[str, int], dict[str, float]]:
    """Choose a vector on the training set only; ties prefer the shipped shape."""
    shipped = dict(CATEGORY_WEIGHTS)
    best_weights: dict[str, int] | None = None
    best_metrics: dict[str, float] | None = None
    best_key: tuple[float, float, float, int] | None = None

    for weights in weight_vectors(step=step, minimum=minimum):
        metrics = evaluate_scored(samples, weights)
        key = (
            metrics["spearman"],
            metrics["pairwise_accuracy"],
            -metrics["mae_points"],
            -_distance(weights, shipped),
        )
        if best_key is None or key > best_key:
            best_key = key
            best_weights = weights
            best_metrics = metrics

    if best_weights is None or best_metrics is None:
        raise StudyError("no weight vector could be evaluated")
    return best_weights, best_metrics


def run_study(
    payload: Any,
    *,
    min_samples: int = MIN_SAMPLES,
    kappa_target: float = KAPPA_TARGET,
    train_fraction: float = 0.5,
    step: int = 10,
) -> dict[str, Any]:
    """Run the full protocol and return a reproducible report."""
    samples, basis = validate_corpus(payload, min_samples=min_samples)
    train, holdout = split_samples(samples, fraction=train_fraction)
    train_ids = {sample.id for sample in train}
    scored = score_samples(samples)
    train_scored = [sample for sample in scored if sample.sample.id in train_ids]
    holdout_ids = {sample.id for sample in holdout}
    holdout_scored = [sample for sample in scored if sample.sample.id in holdout_ids]

    kappa = weighted_kappa(
        (sample.rater_a for sample in samples), (sample.rater_b for sample in samples)
    )
    agreement = raw_agreement(
        (sample.rater_a for sample in samples), (sample.rater_b for sample in samples)
    )
    fitted, fitted_train = fit_weights(train_scored, step=step)
    shipped = dict(CATEGORY_WEIGHTS)
    comparison = {
        "shipped": shipped,
        "fitted": fitted,
        "equal_weights": normalise({key: 1 for key in CATEGORY_WEIGHTS}),
        "ats_heavy": {**shipped, "ats_compatibility": 25, "content_quality": 20},
    }
    holdout_results = {
        name: {"weights": weights, **evaluate_scored(holdout_scored, weights)}
        for name, weights in comparison.items()
    }

    shipped_metrics = holdout_results["shipped"]
    fitted_metrics = holdout_results["fitted"]
    improvement = round(fitted_metrics["spearman"] - shipped_metrics["spearman"], 4)

    if kappa < kappa_target:
        status = "not_ready"
        verdict = (
            f"Inter-rater weighted kappa {kappa:.3f} is below the {kappa_target:.2f} target. "
            "Do not present these weights as validated."
        )
    elif improvement >= 0.03 and fitted_metrics["pairwise_accuracy"] >= shipped_metrics["pairwise_accuracy"]:
        status = "candidate_improves"
        verdict = (
            f"The fitted vector improves held-out rank agreement by {improvement:.3f}. "
            "Review the weights and version them explicitly before adoption; this harness never edits them."
        )
    elif shipped_metrics["spearman"] >= 0.8:
        status = "supported"
        verdict = (
            f"The shipped vector tracks reviewer consensus on the held-out split "
            f"(rho {shipped_metrics['spearman']:.3f}). This supports, but does not prove, the weights."
        )
    else:
        status = "inconclusive"
        verdict = (
            f"The shipped vector reaches rho {shipped_metrics['spearman']:.3f} on the held-out split. "
            "Collect more ratings or revise the rubric before changing weights."
        )

    return {
        "protocol": "consent-gated 200+ resume study, two raters, deterministic 50/50 split",
        "corpus": {"samples": len(samples), "consent_basis": basis},
        "inter_rater": {
            "weighted_kappa": kappa,
            "raw_agreement": agreement,
            "spearman": spearman([s.rater_a for s in samples], [s.rater_b for s in samples]),
            "target_kappa": kappa_target,
        },
        "split": {
            "method": "ascending SHA-256(sample.id), first fraction is train",
            "train": len(train),
            "holdout": len(holdout),
            "fraction": train_fraction,
        },
        "train": {"fitted_weights": fitted, "fitted_metrics": fitted_train},
        "holdout": holdout_results,
        "status": status,
        "verdict": verdict,
        "note": (
            "Point estimates from one split, without confidence intervals. "
            "Weights are never changed automatically."
        ),
    }
