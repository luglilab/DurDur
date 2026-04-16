from __future__ import annotations

from typing import Dict, Iterable, Optional, Sequence, Union

import pandas as pd

from .engines import run_flowai, run_flowclean, run_peacoqc
from .io import load_samples
from .models import CombinedQCResult, SampleResult
from .preprocessing import remove_doublets as _remove_doublets
from .preprocessing import remove_margins as _remove_margins
from .recommendations import build_recommendation
from .reports import generate_reports
from .utils import choose_fluorescence_like_channels, ensure_dataframe, infer_time_channel


def remove_margins(*args, **kwargs):
    return _remove_margins(*args, **kwargs)


def remove_doublets(*args, **kwargs):
    return _remove_doublets(*args, **kwargs)


def _combine_good_indices(length: int, engine_results: Dict[str, object], strategy: str = "majority") -> Sequence[int]:
    if not engine_results:
        return list(range(length))
    sets = [set(result.good_indices) for result in engine_results.values()]
    if strategy == "intersection":
        combined = set.intersection(*sets) if sets else set(range(length))
        return sorted(combined)
    if strategy == "union":
        combined = set.union(*sets) if sets else set(range(length))
        return sorted(combined)
    if strategy == "majority":
        threshold = max(1, (len(sets) // 2) + 1)
        votes = {}
        for good_set in sets:
            for idx in good_set:
                votes[idx] = votes.get(idx, 0) + 1
        return sorted(idx for idx, count in votes.items() if count >= threshold)
    raise ValueError("Unsupported combination strategy: {0}".format(strategy))


def run_qc(
    data,
    engine: str = "combined",
    combination_strategy: str = "majority",
    report_dir: Optional[str] = None,
    preprocess_margins: bool = False,
    preprocess_doublets: bool = False,
    margin_channels: Optional[Sequence[str]] = None,
    doublet_channels: Sequence[str] = ("FSC-A", "FSC-H"),
    flowclean_markers: Optional[Sequence[str]] = None,
    peacoqc_channels: Optional[Sequence[str]] = None,
    flowai_kwargs: Optional[Dict] = None,
    flowclean_kwargs: Optional[Dict] = None,
    peacoqc_kwargs: Optional[Dict] = None,
) -> CombinedQCResult:
    flowai_kwargs = flowai_kwargs or {}
    flowclean_kwargs = flowclean_kwargs or {}
    peacoqc_kwargs = peacoqc_kwargs or {}

    samples = []
    for name, source_path, df, metadata in load_samples(data):
        raw = ensure_dataframe(df)
        preprocessed = raw.copy()
        preprocessing = {}

        if preprocess_margins:
            margin_res = _remove_margins(preprocessed, channels=margin_channels)
            preprocessed = margin_res["frame"]
            preprocessing["margins"] = {"removed": len(margin_res["indices_margins"])}

        if preprocess_doublets:
            doublet_res = _remove_doublets(
                preprocessed,
                channel1=doublet_channels[0],
                channel2=doublet_channels[1],
            )
            preprocessed = doublet_res["frame"]
            preprocessing["doublets"] = {"removed": len(doublet_res["indices_doublets"])}

        engine_results = {}
        if engine in {"flowai", "combined"}:
            engine_results["flowai"] = run_flowai(preprocessed, metadata=metadata, **flowai_kwargs)
        if engine in {"flowclean", "combined"}:
            time_channel = infer_time_channel(preprocessed)
            markers = list(flowclean_markers or choose_fluorescence_like_channels(preprocessed, limit=10, time_channel=time_channel))
            engine_results["flowclean"] = run_flowclean(preprocessed, markers=markers, **flowclean_kwargs)
        if engine in {"peacoqc", "combined"}:
            time_channel = infer_time_channel(preprocessed)
            channels = list(peacoqc_channels or choose_fluorescence_like_channels(preprocessed, limit=12, time_channel=time_channel))
            engine_results["peacoqc"] = run_peacoqc(preprocessed, channels=channels, **peacoqc_kwargs)
        if engine not in {"flowai", "flowclean", "peacoqc", "combined"}:
            raise ValueError("Unsupported engine: {0}".format(engine))

        good_indices = _combine_good_indices(len(preprocessed), engine_results, strategy=combination_strategy)
        final = preprocessed.iloc[list(good_indices)].reset_index(drop=True)
        sample_result = SampleResult(
            name=name,
            source_path=source_path,
            raw=raw,
            preprocessed=preprocessed,
            final=final,
            final_good_indices=list(good_indices),
            final_bad_indices=sorted(set(range(len(preprocessed))) - set(good_indices)),
            preprocessing=preprocessing,
            engine_results=engine_results,
        )
        sample_result.recommendation = build_recommendation(sample_result)
        samples.append(sample_result)

    result = CombinedQCResult(samples=samples)
    if report_dir:
        generate_reports(result, report_dir)
    return result
