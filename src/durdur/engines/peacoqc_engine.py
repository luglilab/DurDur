from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde

from ..models import EngineResult
from ..utils import chunks_with_overlap, infer_time_channel, mad, qc_series


def _find_events_per_bin(df: pd.DataFrame, channels: Sequence[str], remove_zeros: bool, min_cells: int, max_bins: int, step: int) -> int:
    nr_events = len(df)
    if remove_zeros and channels:
        nonzero = min(int(np.sum(pd.to_numeric(df[channel], errors="coerce").fillna(0.0).to_numpy() != 0)) for channel in channels)
        max_bins = min(max_bins, max(1, nonzero // max(min_cells, 1)))
    max_cells = int(np.ceil((nr_events / max(max_bins, 1)) * 2))
    max_cells = ((max_cells // step) * step) + step
    return max(min_cells, max_cells)


def _determine_peaks(values: np.ndarray, remove_zeros: bool, peak_removal: float) -> np.ndarray:
    data = values[np.isfinite(values)]
    if remove_zeros:
        data = data[data != 0]
    if len(data) < 3:
        return np.array([])
    if np.all(data == data[0]):
        return np.array([data[0]])
    density = gaussian_kde(data)
    xs = np.linspace(np.min(data), np.max(data), num=256)
    ys = density(xs)
    idx = np.where((ys[1:-1] > ys[:-2]) & (ys[1:-1] > ys[2:]) & (ys[1:-1] > peak_removal * np.max(ys)))[0] + 1
    if len(idx) == 0:
        return np.array([xs[int(np.argmax(ys))]])
    return xs[idx]


def _determine_all_peaks(df: pd.DataFrame, channels: Sequence[str], breaks: Sequence[np.ndarray], remove_zeros: bool, peak_removal: float) -> Dict[str, pd.DataFrame]:
    results = {}
    for channel in channels:
        peaks = []
        values = pd.to_numeric(df[channel], errors="coerce").to_numpy(dtype=float)
        for i, chunk in enumerate(breaks, start=1):
            found = _determine_peaks(values[chunk], remove_zeros=remove_zeros, peak_removal=peak_removal)
            for peak in found:
                peaks.append({"Bin": i, "Peak": float(peak)})
        if peaks:
            peak_frame = pd.DataFrame(peaks)
            medians = sorted(peak_frame["Peak"].groupby(peak_frame["Peak"].round(2)).median().tolist())
            if medians:
                peak_frame["Cluster"] = peak_frame["Peak"].apply(lambda x: int(np.argmin(np.abs(np.asarray(medians) - x))) + 1)
            else:
                peak_frame["Cluster"] = 1
            results[channel] = peak_frame
    return results


def _flatten_peaks(peak_frames: Dict[str, pd.DataFrame], n_bins: int) -> pd.DataFrame:
    cols = {}
    for channel, frame in peak_frames.items():
        for cluster in sorted(frame["Cluster"].unique()):
            sub = frame[frame["Cluster"] == cluster]
            vector = np.repeat(float(np.median(sub["Peak"])), n_bins)
            vector[sub["Bin"].astype(int).to_numpy() - 1] = sub["Peak"].to_numpy(dtype=float)
            cols["{0}_cluster_{1}".format(channel, cluster)] = vector
    return pd.DataFrame(cols)


def _simple_isolation_mask(matrix: pd.DataFrame, gain_limit: float) -> np.ndarray:
    if matrix.empty:
        return np.ones(0, dtype=bool)
    centered = matrix.apply(lambda col: (col - col.median()) / (1.4826 * mad(col.to_numpy(dtype=float)) + 1e-9))
    score = centered.abs().sum(axis=1).to_numpy()
    return score <= (1.0 / max(gain_limit, 1e-6))


def _mad_outlier_mask(matrix: pd.DataFrame, mad_width: float) -> np.ndarray:
    if matrix.empty:
        return np.ones(0, dtype=bool)
    keep = np.ones(len(matrix), dtype=bool)
    for column in matrix.columns:
        signal = matrix[column].to_numpy(dtype=float)
        center = float(np.median(signal))
        width = 1.4826 * mad(signal)
        if width == 0:
            continue
        keep &= np.abs(signal - center) <= (mad_width * width)
    return keep


def _removed_cells_from_bins(breaks: Sequence[np.ndarray], bad_bins: np.ndarray, nr_cells: int) -> np.ndarray:
    selected = [breaks[i] for i, flag in enumerate(bad_bins) if flag]
    bad_ids = np.concatenate(selected) if selected else np.array([], dtype=int)
    mask = np.ones(nr_cells, dtype=bool)
    if len(bad_ids):
        mask[np.unique(bad_ids)] = False
    return mask


def _remove_short_regions(good_bins: np.ndarray, consecutive_bins: int) -> np.ndarray:
    updated = good_bins.copy()
    start = 0
    n = len(updated)
    while start < n:
        end = start + 1
        while end < n and updated[end] == updated[start]:
            end += 1
        if updated[start] and (end - start) < consecutive_bins:
            updated[start:end] = False
        start = end
    return updated


def run_peacoqc(
    df: pd.DataFrame,
    channels: Sequence[str],
    determine_good_cells: str = "all",
    min_cells: int = 150,
    max_bins: int = 500,
    step: int = 500,
    mad_width: float = 6.0,
    it_limit: float = 0.6,
    consecutive_bins: int = 5,
    remove_zeros: bool = False,
    force_it: int = 150,
    peak_removal: float = 1.0 / 3.0,
) -> EngineResult:
    channels = [channel for channel in channels if channel in df.columns]
    events_per_bin = _find_events_per_bin(df, channels, remove_zeros, min_cells, max_bins, step)
    breaks = chunks_with_overlap(len(df), events_per_bin, int(np.ceil(events_per_bin / 2.0)))
    peak_frames = _determine_all_peaks(df, channels, breaks, remove_zeros, peak_removal)
    peak_matrix = _flatten_peaks(peak_frames, len(breaks))

    outlier_bins = np.ones(len(breaks), dtype=bool)
    it_mask = np.ones(len(breaks), dtype=bool)
    mad_mask = np.ones(len(breaks), dtype=bool)

    if determine_good_cells in {"all", "IT"} and len(breaks) >= force_it:
        it_mask = _simple_isolation_mask(peak_matrix, gain_limit=it_limit)
        outlier_bins &= it_mask

    if determine_good_cells in {"all", "MAD"}:
        mad_mask = _mad_outlier_mask(peak_matrix.loc[outlier_bins], mad_width=mad_width)
        if len(mad_mask):
            outlier_bins[outlier_bins] = mad_mask

    if determine_good_cells in {"all", "IT", "MAD"}:
        outlier_bins = _remove_short_regions(outlier_bins, consecutive_bins=consecutive_bins)
        good_mask = _removed_cells_from_bins(breaks, ~outlier_bins, len(df))
    else:
        good_mask = np.ones(len(df), dtype=bool)

    good = np.flatnonzero(good_mask).tolist()
    bad = np.flatnonzero(~good_mask).tolist()
    return EngineResult(
        engine="peacoqc",
        good_indices=good,
        bad_indices=bad,
        qc_vector=qc_series(good, bad, len(df)),
        details={
            "events_per_bin": events_per_bin,
            "n_bins": len(breaks),
            "peak_frames": peak_frames,
            "it_kept_bins": int(np.sum(it_mask)),
            "mad_kept_bins": int(np.sum(mad_mask)),
            "time_channel": infer_time_channel(df),
        },
    )
