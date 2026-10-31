"""The calibration maths must be right before its verdict can be trusted."""

from __future__ import annotations

from app.intelligence.scoring.calibration import (
    assess,
    build_sample,
    normalise,
    spearman,
    weighted_total,
)
from app.schemas.resume import ResumeStructure


def test_spearman_is_exact_for_monotone_data() -> None:
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0


def test_spearman_handles_ties_without_inventing_order() -> None:
    # Tied tiers still correlate perfectly with identical scores.
    assert spearman([1, 1, 2], [5, 5, 9]) == 1.0


def test_weighted_total_ignores_categories_that_did_not_apply() -> None:
    scores = {"content_quality": 80.0, "language_readability": 60.0}
    weights = {"content_quality": 25, "experience": 20, "language_readability": 10}

    # Experience is missing from the scores, so its weight leaves the denominator.
    assert weighted_total(scores, weights) == round((25 * 80 + 10 * 60) / 35, 2)


def test_a_better_resume_scores_higher_under_the_shipped_vector() -> None:
    strong = build_sample(
        "strong",
        5,
        ResumeStructure(),
        {"content_quality": 92.0, "experience": 90.0, "skills": 85.0, "structure": 100.0,
         "ats_compatibility": 95.0, "language_readability": 88.0},
    )
    weak = build_sample(
        "weak",
        2,
        ResumeStructure(),
        {"content_quality": 45.0, "experience": 40.0, "skills": 30.0, "structure": 55.0,
         "ats_compatibility": 62.0, "language_readability": 48.0},
    )

    metrics = assess([strong, weak], normalise({k: v for k, v in {"content_quality": 25}.items()} | {
        "experience": 20,
        "skills": 15,
        "structure": 15,
        "ats_compatibility": 15,
        "language_readability": 10,
    }))

    assert metrics["spearman"] == 1.0
    assert metrics["pairwise_accuracy"] == 1.0
    assert metrics["tier_spread"] > 0


def test_normalise_scales_any_vector_to_one_hundred() -> None:
    scaled = normalise({"a": 1, "b": 1, "c": 2})
    assert sum(scaled.values()) == 100
