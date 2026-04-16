from __future__ import annotations

import math
from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

from ..models import EngineResult
from ..utils import infer_time_channel, infer_timestep, mad, order_by_time, qc_series, select_channels


def _detect_frequency_anomalies(counts: np.ndarray, alpha: float = 3.5) -> np.ndarray:
    if len(counts) < 3:
        return np.zeros(len(counts), dtype=bool)
    center = float(np.median(counts))
    width = 1.4826 * mad(counts)
    if width == 0:
        return np.zeros(len(counts), dtype=bool)
    return np.abs(counts - center) > alpha * width


def _flow_rate(df: pd.DataFrame, time_channel: str, second_fraction: float, timestep: float) -> Dict:
    values = pd.to_numeric(df[time_channel], errors="coerce").fillna(0.0).to_numpy()
    endsec = int(math.ceil(timestep * np.max(values))) if len(values) else 0
    tbins = np.arange(0, endsec / timestep + (second_fraction / timestep), second_fraction / timestep)
    counts, _ = np.histogram(values, bins=tbins)
    anomaly_bins = _detect_frequency_anomalies(counts)
    event_bins = np.digitize(values, tbins[1:], right=False)
    bad_idx = np.flatnonzero(anomaly_bins[np.clip(event_bins, 0, max(len(counts) - 1, 0))]).tolist() if len(counts) else []
    return {
        "counts": counts.tolist(),
        "bin_edges": tbins.tolist(),
        "bad_indices": bad_idx,
    }


def _contiguous_runs(mask: np.ndarray) -> list:
    runs = []
    start = None
    for i, value in enumerate(mask, start=1):
        if value and start is None:
            start = i
        elif not value and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def _flow_signal(df: pd.DataFrame, channels: Sequence[str], bin_size: int, max_cpt: int, outlier_bins: bool) -> Dict:
    if not channels:
        return {"bad_indices": [], "changepoints": {}, "outlier_bin_ids": []}
    cf = np.repeat(np.arange(1, len(df) // bin_size + 1), bin_size)
    remainder = len(df) - len(cf)
    if remainder > 0:
        cf = np.concatenate((cf, np.repeat((len(df) // bin_size) + 1, remainder)))
    grouped = pd.DataFrame(df[list(channels)]).assign(cf=cf).groupby("cf", sort=True).median()
    robust_scaled = grouped.apply(
        lambda col: (col - col.median()) / (1.4826 * mad(col.to_numpy(dtype=float)) + 1e-9)
    )
    score = robust_scaled.abs().median(axis=1).to_numpy()
    diff_score = np.r_[0.0, np.abs(np.diff(score))]

    score_width = 1.4826 * mad(score)
    diff_width = 1.4826 * mad(diff_score)
    score_threshold = np.median(score) + 6.0 * score_width
    diff_threshold = np.median(diff_score) + 8.0 * diff_width

    outlier_mask = score > score_threshold
    transition_mask = diff_score > diff_threshold

    # Extend transitions slightly to avoid keeping narrow unstable seams.
    unstable = outlier_mask | transition_mask | np.r_[transition_mask[1:], False] | np.r_[False, transition_mask[:-1]]
    stable_bins_mask = ~unstable

    runs = _contiguous_runs(stable_bins_mask)
    if not runs:
        stable = (1, len(grouped))
        stable_bins_mask = np.ones(len(grouped), dtype=bool)
    else:
        stable = max(runs, key=lambda item: item[1] - item[0] + 1)

    changepoints = {}
    for column in grouped.columns:
        signal = grouped[column].to_numpy(dtype=float)
        diffs = np.abs(np.diff(signal))
        if len(diffs) == 0:
            changepoints[column] = []
            continue
        take = min(max_cpt, len(diffs))
        order = np.argsort(diffs)[::-1][:take]
        changepoints[column] = sorted((order + 1).tolist())

    stable_bin_ids = set(np.flatnonzero(stable_bins_mask) + 1)
    event_bin_ids = pd.Series(cf)
    good_mask = event_bin_ids.isin(stable_bin_ids)
    if outlier_bins and np.any(outlier_mask):
        outlier_bin_ids = set(np.flatnonzero(outlier_mask) + 1)
        good_mask &= ~event_bin_ids.isin(outlier_bin_ids)
    bad_idx = np.flatnonzero(~good_mask.to_numpy()).tolist()
    return {
        "bad_indices": bad_idx,
        "changepoints": changepoints,
        "stable_segment": stable,
        "outlier_bin_ids": (np.flatnonzero(outlier_mask) + 1).tolist(),
        "score_threshold": float(score_threshold),
        "diff_threshold": float(diff_threshold),
    }


def _flow_margin(df: pd.DataFrame, channels: Sequence[str], side: str, neg_values: bool) -> Dict:
    bad = set()
    summary = {}
    for channel in channels:
        values = pd.to_numeric(df[channel], errors="coerce").to_numpy(dtype=float)
        lower = []
        upper = []
        if side in {"lower", "both"}:
            if neg_values:
                negative = values[values < 0]
                if len(negative):
                    cutoff = float(np.median(negative) - 3.5 * 1.4826 * mad(negative))
                    lower = np.flatnonzero(values <= cutoff).tolist()
                else:
                    lower = np.flatnonzero(values <= np.min(values)).tolist()
            else:
                lower = np.flatnonzero(values <= np.min(values)).tolist()
        if side in {"upper", "both"}:
            upper = np.flatnonzero(values >= np.max(values)).tolist()
        bad.update(lower)
        bad.update(upper)
        summary[channel] = {"lower": len(lower), "upper": len(upper)}
    return {"bad_indices": sorted(bad), "summary": summary}


def run_flowai(
    df: pd.DataFrame,
    metadata: Optional[Dict] = None,
    time_channel: Optional[str] = None,
    second_fraction: float = 0.1,
    fs_exclude: Optional[Sequence[str]] = None,
    fm_exclude: Optional[Sequence[str]] = None,
    max_cpt: int = 3,
    outlier_bins: bool = False,
    margin_side: str = "both",
    neg_values: bool = True,
) -> EngineResult:
    metadata = metadata or {}
    local_time = infer_time_channel(df, preferred=time_channel)
    ordered = order_by_time(df, local_time)
    timestep = infer_timestep(ordered, metadata, local_time)
    all_idx = set(range(len(ordered)))

    if local_time is None:
        fr = {"bad_indices": [], "counts": [], "bin_edges": []}
    else:
        fr = _flow_rate(ordered, local_time, second_fraction=max(second_fraction, timestep), timestep=timestep)

    fs_channels = select_channels(ordered, exclude_patterns=list(fs_exclude or []) + ([local_time] if local_time else []))
    fm_channels = select_channels(ordered, exclude_patterns=list(fm_exclude or []) + ([local_time] if local_time else []))
    fs = _flow_signal(ordered, fs_channels, bin_size=max(1, min(500, len(ordered) // 100 or 1)), max_cpt=max_cpt, outlier_bins=outlier_bins)
    fm = _flow_margin(ordered, fm_channels, side=margin_side, neg_values=neg_values)

    bad = set(fr["bad_indices"]) | set(fs["bad_indices"]) | set(fm["bad_indices"])
    good = sorted(all_idx - bad)
    bad = sorted(bad)
    return EngineResult(
        engine="flowai",
        good_indices=good,
        bad_indices=bad,
        qc_vector=qc_series(good, bad, len(ordered)),
        details={"flow_rate": fr, "flow_signal": fs, "flow_margin": fm, "time_channel": local_time},
    )
