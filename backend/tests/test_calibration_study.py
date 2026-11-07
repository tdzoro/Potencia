"""The study harness must refuse weak corpora before it reports a number."""

from __future__ import annotations

import pytest

from app.intelligence.scoring.study import (
    MIN_SAMPLES,
    StudyError,
    evaluate_scored,
    fit_weights,
    raw_agreement,
    run_study,
    score_samples,
    split_samples,
    validate_corpus,
    weight_vectors,
    weighted_kappa,
)

RESUME = """ALEX MORGAN
alex.morgan@example.com

SUMMARY
Backend engineer with five years building payment services.

TECHNICAL SKILLS
Python, PostgreSQL, Kubernetes

WORK EXPERIENCE
Backend Engineer
Acme Payments | Jan 2021 - Present
- Built a ledger service handling 2M daily transactions
- Reduced p99 latency by 40 percent

EDUCATION
B.Tech in Computer Science
State University | 2013 - 2017
"""


def _payload(count: int = 4, *, consent: bool = True) -> dict:
    return {
        "consent": {
            "confirmed": consent,
            "anonymised": True,
            "basis": "Written consent recorded for an internal calibration study.",
        },
        "samples": [
            {
                "id": f"sample-{index}",
                "text": RESUME,
                "rater_a": (index % 5) + 1,
                "rater_b": (index % 5) + 1,
            }
            for index in range(count)
        ],
    }


def test_default_protocol_requires_two_hundred_resumes() -> None:
    with pytest.raises(StudyError, match=str(MIN_SAMPLES)):
        validate_corpus(_payload(2))


def test_consent_and_anonymity_are_mandatory() -> None:
    without_consent = _payload(2)
    without_consent["consent"]["confirmed"] = False
    with pytest.raises(StudyError, match="consent.confirmed"):
        validate_corpus(without_consent, min_samples=2)

    not_anonymised = _payload(2)
    not_anonymised["consent"]["anonymised"] = False
    with pytest.raises(StudyError, match="anonymised"):
        validate_corpus(not_anonymised, min_samples=2)


def test_bad_ratings_are_rejected() -> None:
    payload = _payload(2)
    payload["samples"][0]["rater_a"] = 6
    with pytest.raises(StudyError, match="rater_a"):
        validate_corpus(payload, min_samples=2)


def test_duplicate_ids_are_rejected() -> None:
    payload = _payload(2)
    payload["samples"][1]["id"] = payload["samples"][0]["id"]
    with pytest.raises(StudyError, match="unique"):
        validate_corpus(payload, min_samples=2)


def test_weighted_kappa_is_one_for_perfect_agreement() -> None:
    assert weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == 1.0
    assert raw_agreement([1, 2, 3], [1, 2, 3]) == 1.0


def test_weighted_kappa_penalises_systematic_disagreement() -> None:
    assert weighted_kappa([1, 2, 3, 4], [5, 4, 3, 2]) < 1
    assert weighted_kappa([1, 1, 2, 2], [1, 2, 2, 2]) < 1
    assert raw_agreement([1, 1, 5, 5], [5, 5, 1, 1]) == 0.0


def test_split_is_deterministic_disjoint_and_fractional() -> None:
    samples, _ = validate_corpus(_payload(10), min_samples=2)

    first_train, first_holdout = split_samples(samples, fraction=0.6)
    second_train, second_holdout = split_samples(samples, fraction=0.6)

    assert [sample.id for sample in first_train] == [sample.id for sample in second_train]
    assert [sample.id for sample in first_holdout] == [sample.id for sample in second_holdout]
    assert len(first_train) == 6
    assert len(first_holdout) == 4
    assert not {sample.id for sample in first_train} & {
        sample.id for sample in first_holdout
    }


def test_weight_grid_sums_to_one_hundred() -> None:
    vectors = list(weight_vectors(step=10, minimum=10))

    assert len(vectors) == 126
    assert all(sum(vector.values()) == 100 for vector in vectors)


def test_fit_weights_returns_a_normalised_vector() -> None:
    samples, _ = validate_corpus(_payload(6), min_samples=2)
    scored = score_samples(samples)

    weights, metrics = fit_weights(scored)

    assert sum(weights.values()) == 100
    assert set(weights) == {
        "content_quality",
        "experience",
        "skills",
        "structure",
        "ats_compatibility",
        "language_readability",
    }
    assert "spearman" in metrics


def test_study_reports_inter_rater_agreement_before_holdout_metrics() -> None:
    report = run_study(_payload(8), min_samples=4)

    assert report["corpus"]["samples"] == 8
    assert report["inter_rater"]["weighted_kappa"] == 1.0
    assert report["split"]["train"] + report["split"]["holdout"] == 8
    assert set(report["holdout"]) == {"shipped", "fitted", "equal_weights", "ats_heavy"}
    assert report["status"] in {"supported", "inconclusive", "candidate_improves", "not_ready"}


def test_low_agreement_blocks_a_validation_claim() -> None:
    payload = _payload(8)
    for index, sample in enumerate(payload["samples"]):
        sample["rater_a"] = 1 if index % 2 else 5
        sample["rater_b"] = 5 if index % 2 else 1

    report = run_study(payload, min_samples=4)

    assert report["inter_rater"]["weighted_kappa"] < 0.7
    assert report["status"] == "not_ready"
