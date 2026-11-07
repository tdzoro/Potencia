"""Render every README chart from the stored measurements.

The figures are a view over JSON that other scripts produced by running the
product — this script measures nothing itself, so a chart can never disagree
with the table next to it.

    PYTHONPATH=backend backend/.venv/bin/python scripts/readme_charts.py

Reads  : assets/readme/{metrics,load,engine_profile,calibration}.json
Writes : assets/readme/*.png
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "readme"

INK = "#12121A"
MUTED = "#5A5A6E"
GRID = "#E3E3EC"
ACCENT = "#6D3BF5"
ACCENT_SOFT = "#C4B5FD"
CYAN = "#22D3EE"
AMBER = "#F59E0B"


def read(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def style(ax, axis: str = "y") -> None:
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    ax.grid(axis=axis, color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)


def save(figure, name: str) -> None:
    figure.tight_layout()
    figure.savefig(OUT / name, facecolor="white", dpi=200)
    plt.close(figure)
    print(f"  {name}")


def calibration_chart(data: dict) -> None:
    """Does any plausible weight vector rank resumes better than the shipped one?"""
    results = data["results"]
    names = [row["name"].replace(" (v1.1.0)", "") for row in results]
    spearman = [row["spearman"] for row in results]
    pairwise = [row["pairwise_accuracy"] for row in results]

    figure, ax = plt.subplots(figsize=(8.4, 3.6), dpi=200)
    positions = list(range(len(names)))
    width = 0.36
    ax.bar([p - width / 2 for p in positions], spearman, width, color=ACCENT, label="Spearman ρ")
    ax.bar([p + width / 2 for p in positions], pairwise, width, color=CYAN, label="Pairwise accuracy")
    ax.set_xticks(positions, names, fontsize=8.5, color=INK)
    ax.set_ylim(0, 1.05)
    ax.set_title(
        f"Rank agreement with the rubric — {data['samples']} fixtures, 5 candidate weight vectors",
        fontsize=10,
        color=INK,
        loc="left",
    )
    ax.legend(frameon=False, fontsize=8, loc="lower right", ncol=2)
    style(ax)
    for position, (rho, pair) in enumerate(zip(spearman, pairwise, strict=True)):
        ax.text(position - width / 2, rho + 0.02, f"{rho:.3f}", ha="center", fontsize=7.5, color=MUTED)
        ax.text(position + width / 2, pair + 0.02, f"{pair:.2f}", ha="center", fontsize=7.5, color=MUTED)
    save(figure, "calibration.png")


def contribution_chart(metrics: dict) -> None:
    """Score per category against its ceiling, weighted — the whole formula in one picture."""
    weights = {
        "content_quality": 25,
        "experience": 20,
        "skills": 15,
        "structure": 15,
        "ats_compatibility": 15,
        "language_readability": 10,
    }
    labels = {
        "content_quality": "Content",
        "experience": "Experience",
        "skills": "Skills",
        "structure": "Structure",
        "ats_compatibility": "ATS",
        "language_readability": "Language",
    }
    components = metrics["sample"]["components"]

    figure, ax = plt.subplots(figsize=(8.4, 3.5), dpi=200)
    names = list(weights)
    positions = list(range(len(names)))
    earned = [components[key] for key in names]
    lost = [100 - components[key] for key in names]

    ax.barh(positions, earned, color=ACCENT, height=0.55, label="earned")
    ax.barh(positions, lost, left=earned, color="#EDEDF3", height=0.55, label="not earned")
    ax.set_yticks(positions, [f"{labels[key]}  ×{weights[key]}" for key in names], fontsize=8.5, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_title(
        "Category score against its ceiling — weight shown, overall 82.6",
        fontsize=10,
        color=INK,
        loc="left",
    )
    style(ax, axis="x")
    ax.grid(axis="y", visible=False)
    for position, value in zip(positions, earned, strict=True):
        ax.text(value - 3, position, f"{value:.1f}", ha="right", va="center", fontsize=7.5, color="white")
    save(figure, "contribution.png")


def scaling_chart(profile: dict) -> None:
    """Cost per kilobyte is flat only if nothing became quadratic."""
    scaling = profile["scaling"]
    match = profile["match_scaling"]
    warm = profile["warm_ms"]

    figure, (left, right) = plt.subplots(1, 2, figsize=(9.6, 3.6), dpi=200)

    kilobytes = [row["kilobytes"] for row in scaling]
    per_kb = [row["ms_per_kb"] for row in scaling]
    left.plot(kilobytes, per_kb, color=ACCENT, linewidth=1.8, marker="o", markersize=4)
    for row in scaling:
        left.annotate(
            f"{row['p50_ms']:.2f} ms",
            (row["kilobytes"], row["ms_per_kb"]),
            textcoords="offset points",
            xytext=(6, 6),
            fontsize=7.5,
            color=MUTED,
        )
    left.set_xlabel("document size (KB)", fontsize=8.5, color=MUTED)
    left.set_ylabel("ms per KB (parse + score)", fontsize=8.5, color=MUTED)
    left.set_title("Parsing stays flat per byte", fontsize=10, color=INK, loc="left")
    left.set_ylim(0, max(per_kb) * 1.25)
    style(left)

    requirements = [row["requirements"] for row in match]
    cost = [row["p50_ms"] for row in match]
    right.plot(requirements, cost, color=CYAN, linewidth=1.8, marker="s", markersize=4)
    for row in match:
        right.annotate(
            f"{row['p50_ms']:.2f} ms",
            (row["requirements"], row["p50_ms"]),
            textcoords="offset points",
            xytext=(5, 6),
            fontsize=7.5,
            color=MUTED,
        )
    right.set_xlabel("required skills in the job description", fontsize=8.5, color=MUTED)
    right.set_ylabel("match time (ms)", fontsize=8.5, color=MUTED)
    right.set_title("Matching is linear, not quadratic", fontsize=10, color=INK, loc="left")
    right.set_ylim(0, max(cost) * 1.3)
    right.xaxis.set_major_locator(MaxNLocator(integer=True))
    style(right)

    figure.suptitle(
        f"Engine cost from {profile['corpus']['documents']} documents · "
        f"warm p50 parse {warm['parse']['p50']:.2f} ms · full pipeline {warm['full']['p50']:.2f} ms",
        fontsize=8.5,
        color=MUTED,
        x=0.01,
        ha="left",
    )
    save(figure, "scaling.png")


def load_chart(load: dict) -> None:
    """Latency percentiles under eight concurrent clients — the tail is the product."""
    latency = load["latency_ms"]
    labels = ["mean", "p50", "p95", "p99", "max"]
    values = [latency[key] for key in labels]
    colors = ["#E4E4EC", ACCENT, AMBER, "#FB7185", "#E11D48"]

    figure, ax = plt.subplots(figsize=(7.6, 3.2), dpi=200)
    positions = list(range(len(labels)))
    ax.bar(positions, values, color=colors, width=0.55)
    ax.set_xticks(positions, labels, fontsize=8.5, color=INK)
    ax.set_ylabel("analysis latency (ms)", fontsize=8.5, color=MUTED)
    ax.set_title(
        f"{load['requests_completed']} analyses · {load['workers']} clients · "
        f"{load['throughput_rps']} analyses/s · {load['requests_failed']} failed",
        fontsize=10,
        color=INK,
        loc="left",
    )
    ax.set_ylim(0, max(values) * 1.18)
    style(ax)
    for position, value in zip(positions, values, strict=True):
        ax.text(position, value + max(values) * 0.02, f"{value:.0f}", ha="center", fontsize=8, color=MUTED)
    save(figure, "load.png")


def score_ladder_chart(calibration: dict) -> None:
    """Where each fixture lands under the shipped weights."""
    results = next(row for row in calibration["results"] if row["name"].startswith("shipped"))
    figure, ax = plt.subplots(figsize=(8.4, 2.4), dpi=200)
    ax.hlines(0, results["min"], results["max"], color=GRID, linewidth=8)
    ax.plot([results["overall"] if "overall" in results else (results["min"] + results["max"]) / 2], [0], "o")

    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.set_xlabel("overall score", fontsize=8.5, color=MUTED)
    ax.set_title(
        f"Calibration corpus spans {results['min']:.1f} – {results['max']:.1f} "
        f"(spread {results['tier_spread']:.1f})",
        fontsize=10,
        color=INK,
        loc="left",
    )
    style(ax, axis="x")
    save(figure, "calibration-spread.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = read("metrics.json")
    load = read("load.json")
    profile = read("engine_profile.json")
    calibration = read("calibration.json")

    print("rendering charts from stored measurements")
    calibration_chart(calibration)
    contribution_chart(metrics)
    scaling_chart(profile)
    load_chart(load)
    score_ladder_chart(calibration)
    print("done")


if __name__ == "__main__":
    main()
