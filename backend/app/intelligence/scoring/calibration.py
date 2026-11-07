"""Weight calibration harness.

The six category weights in `SCORING_METHODOLOGY.md` are product-design
hypotheses. This module makes them *testable* rather than merely disclosed: given
resumes with human-assigned quality tiers, it measures how well a weighting ranks
them, and compares the shipped vector against plausible alternatives.

What this is not: an empirical validation. The reference set is a small authored
fixture set with rubric-assigned tiers, not a recruiter study. A harness that
reports the difference honestly is worth more than a claim that cannot be
checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Iterable

from app.schemas.resume import ResumeStructure
from app.schemas.scores import CATEGORY_WEIGHTS, ScoreCategory

Categories = dict[str, int]


@dataclass(frozen=True)
class Sample:
    name: str
    tier: int
    structure: ResumeStructure
    category_scores: dict[str, float]


@dataclass(frozen=True)
class Candidate:
    name: str
    weights: Categories


def _ranks(values: list[float]) -> list[float]:
    """Competition-free average ranks, so ties do not distort the correlation."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        average = (index + end) / 2 + 1
        for position in range(index, end + 1):
            ranks[order[position]] = average
        index = end + 1
    return ranks


def spearman(xs: Iterable[float], ys: Iterable[float]) -> float:
    """Rank correlation without a statistics dependency."""
    left = list(xs)
    right = list(ys)
    if len(left) != len(right) or len(left) < 2:
        return 0.0

    rank_x, rank_y = _ranks(left), _ranks(right)
    n = len(left)
    mean_x, mean_y = sum(rank_x) / n, sum(rank_y) / n
    numerator = sum((a - mean_x) * (b - mean_y) for a, b in zip(rank_x, rank_y, strict=True))
    denominator = (
        sum((a - mean_x) ** 2 for a in rank_x) ** 0.5
        * sum((b - mean_y) ** 2 for b in rank_y) ** 0.5
    )
    return round(numerator / denominator, 4) if denominator else 0.0


def weighted_total(category_scores: dict[str, float], weights: Categories) -> float:
    """The shipped formula: weighted mean over the categories that applied."""
    applicable = [(weights[key], value) for key, value in category_scores.items() if weights.get(key)]
    total_weight = sum(weight for weight, _ in applicable)
    if not total_weight:
        return 0.0
    return round(sum(weight * value for weight, value in applicable) / total_weight, 2)


def assess(samples: list[Sample], weights: Categories) -> dict[str, float]:
    tiers = [float(sample.tier) for sample in samples]
    totals = [weighted_total(sample.category_scores, weights) for sample in samples]

    # T1: does a better resume always score higher?
    pairwise_correct = pairwise_total = 0
    for left, right in permutations(range(len(samples)), 2):
        if tiers[left] == tiers[right]:
            continue
        pairwise_total += 1
        if (totals[left] > totals[right]) == (tiers[left] > tiers[right]):
            pairwise_correct += 1

    # T2: does the spread between tiers survive, or is everything compressed?
    by_tier: dict[int, list[float]] = {}
    for sample, total in zip(samples, totals, strict=True):
        by_tier.setdefault(sample.tier, []).append(total)
    tier_means = [sum(values) / len(values) for _, values in sorted(by_tier.items())]
    spread = round(tier_means[-1] - tier_means[0], 2) if len(tier_means) >= 2 else 0.0

    return {
        "spearman": spearman(tiers, totals),
        "pairwise_accuracy": round(pairwise_correct / pairwise_total, 4) if pairwise_total else 0.0,
        "tier_spread": spread,
        "min": round(min(totals), 2) if totals else 0.0,
        "max": round(max(totals), 2) if totals else 0.0,
    }


def candidates() -> list[Candidate]:
    """The shipped vector plus the alternatives worth ruling out."""
    shipped: Categories = {key: value for key, value in CATEGORY_WEIGHTS.items()}
    return [
        Candidate("shipped (v1.2.0)", shipped),
        Candidate("content-heavy", {**shipped, "content_quality": 35, "ats_compatibility": 10}),
        Candidate("ats-heavy", {**shipped, "ats_compatibility": 25, "content_quality": 20}),
        Candidate(
            "experience-heavy",
            {**shipped, "experience": 30, "structure": 10, "language_readability": 5},
        ),
        Candidate(
            "equal-weights",
            {key: 100 // len(CATEGORY_WEIGHTS) for key in CATEGORY_WEIGHTS},
        ),
    ]


def normalise(weights: Categories) -> Categories:
    """Scale to exactly 100 so two vectors are comparable.

    Largest-remainder rounding; independently rounding six equal weights to 17
    would report a total of 102 and make the comparison vectors dishonest.
    """
    total = sum(weights.values())
    if total == 0:
        return dict(weights)

    scaled = {key: value * 100 / total for key, value in weights.items()}
    result = {key: int(value) for key, value in scaled.items()}
    remaining = 100 - sum(result.values())
    order = sorted(scaled, key=lambda key: (-(scaled[key] - result[key]), key))
    for key in order[:remaining]:
        result[key] += 1
    return result


def evaluate(samples: list[Sample]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for candidate in candidates():
        weights = normalise(candidate.weights)
        metrics = assess(samples, weights)
        results.append({"name": candidate.name, "weights": weights, **metrics})
    return results


def build_sample(name: str, tier: int, structure: ResumeStructure, category_scores: dict[str, float]) -> Sample:
    return Sample(name=name, tier=tier, structure=structure, category_scores=category_scores)


__all__ = [
    "Candidate",
    "Sample",
    "assess",
    "build_sample",
    "candidates",
    "evaluate",
    "normalise",
    "spearman",
    "weighted_total",
]


def _category_order() -> tuple[ScoreCategory, ...]:
    return tuple(CATEGORY_WEIGHTS.keys())  # type: ignore[return-value]
