from __future__ import annotations

from typing import Dict, List

from .models import SampleResult


def build_recommendation(sample: SampleResult) -> Dict[str, object]:
    n_events = len(sample.preprocessed)
    engine_percents = {
        name: result.percent_removed
        for name, result in sample.engine_results.items()
    }
    notes: List[str] = []
    warnings: List[str] = []

    if n_events < 500:
        warnings.append("Very small sample size. Engine decisions are less stable below 500 events.")
    elif n_events < 5000:
        warnings.append("Small sample size. Conservative interpretation is recommended.")

    recommended_engine = _pick_engine(sample, warnings, notes)

    if "peacoqc" in engine_percents and engine_percents["peacoqc"] >= 99.0:
        warnings.append("PeacoQC-style path removed almost all events on this sample.")
    if "flowai" in engine_percents and engine_percents["flowai"] >= 95.0:
        warnings.append("flowAI-style path removed nearly the entire sample.")
    if "flowclean" in engine_percents and engine_percents["flowclean"] == 0.0 and n_events < 30000:
        notes.append("flowClean-style path stayed permissive, which is expected on small files because the original method assumes larger event counts.")

    final_percent_removed = 0.0 if n_events == 0 else 100.0 * len(sample.final_bad_indices) / n_events
    if final_percent_removed >= 90:
        warnings.append("The current combined result is extremely strict for this sample.")

    summary = _make_summary(recommended_engine, n_events, final_percent_removed, warnings)
    return {
        "recommended_engine": recommended_engine,
        "summary": summary,
        "warnings": warnings,
        "notes": notes,
    }


def _pick_engine(sample: SampleResult, warnings: List[str], notes: List[str]) -> str:
    n_events = len(sample.preprocessed)
    results = sample.engine_results
    engine_percents = {name: result.percent_removed for name, result in results.items()}

    if not results:
        notes.append("No engine results were available.")
        return "none"

    if n_events < 5000:
        if "flowai" in results:
            notes.append("For small samples, flowAI-style checks are preferred in this integrated port because flowClean and PeacoQC are more sensitive to low event counts.")
            return "flowai"

    non_extreme = [
        name for name, percent in engine_percents.items()
        if 0.0 < percent < 95.0
    ]
    if len(non_extreme) == 1:
        notes.append("Only one engine produced a non-extreme removal rate.")
        return non_extreme[0]

    if "flowai" in results and engine_percents.get("peacoqc", 0.0) >= 99.0:
        notes.append("PeacoQC-style output is likely too aggressive here, so flowAI is the safer default.")
        return "flowai"

    if "flowclean" in results and n_events >= 30000 and engine_percents["flowclean"] > 0:
        notes.append("Large sample with non-zero flowClean removals, so composition-based stability is likely informative.")
        return "flowclean"

    ranked = sorted(engine_percents.items(), key=lambda item: abs(item[1] - 15.0))
    if ranked:
        notes.append("Fallback recommendation based on the least extreme removal profile.")
        return ranked[0][0]
    return "none"


def _make_summary(recommended_engine: str, n_events: int, final_percent_removed: float, warnings: List[str]) -> str:
    if recommended_engine == "none":
        return "No engine recommendation is available."
    if n_events < 5000:
        return (
            "This sample is small, so the recommended engine is {0}. "
            "Treat the combined result carefully, especially when removals exceed {1:.1f}%."
        ).format(recommended_engine, final_percent_removed)
    if warnings:
        return (
            "The recommended engine is {0}. Review the warnings before relying on the combined output."
        ).format(recommended_engine)
    return "The recommended engine is {0} based on the current removal patterns.".format(recommended_engine)
