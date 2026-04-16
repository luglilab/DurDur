from __future__ import annotations

from collections import Counter
from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

from ..models import EngineResult
from ..utils import infer_time_channel, mad, order_by_time, qc_series


def _make_bins(values: np.ndarray, n_bins: int) -> list:
    if len(values) == 0:
        return []
    minimum = float(np.min(values))
    if minimum > 0:
        values = values - minimum
    end = float(values[-1]) if len(values) else 0.0
    step = end / n_bins if n_bins else 1.0
    bins = []
    for i in range(1, n_bins + 1):
        left = (i - 1) * step
        right = i * step
        idx = np.where((values >= left) & (values < right))[0]
        if i == n_bins:
            idx = np.where(values >= left)[0]
        bins.append(idx)
    return bins


def _make_pop_codes(frame: pd.DataFrame, cutoff) -> np.ndarray:
    data = frame.to_numpy(dtype=float)
    if cutoff == "median":
        thresholds = np.median(data, axis=0)
    elif isinstance(cutoff, float) and cutoff < 1:
        thresholds = np.quantile(data, cutoff, axis=0)
    else:
        thresholds = np.repeat(float(cutoff), data.shape[1])

    binary = np.zeros_like(data, dtype=int)
    for i in range(data.shape[1]):
        channel = data[:, i]
        threshold = thresholds[i]
        if np.mean(channel > threshold) > 0.9:
            threshold = np.median(channel)
        binary[:, i] = (channel > threshold).astype(int)

    weights = 2 ** np.arange(binary.shape[1])
    return (binary * weights).sum(axis=1)


def _clr(matrix: np.ndarray, minim: float = 1e-7) -> np.ndarray:
    sums = matrix.sum(axis=0)
    ta = minim / max(np.max(sums), minim)
    zero_counts = (matrix == 0).sum(axis=0)
    n = matrix.shape[0]
    m = int(np.max(zero_counts))
    if n == m:
        n += 1
    d = (n ** 2 * ta) / ((m + 1) * max((n - m), 1))
    ts = (d * m * (m + 1)) / (n ** 2)
    revised = np.where(matrix == 0, ta, matrix - (matrix * ts))
    revised = np.clip(revised, 1e-12, None)
    gmeans = np.exp(np.mean(np.log(revised), axis=0))
    return np.log(revised / gmeans)


def _flag_unlikely(sum_counts: np.ndarray) -> np.ndarray:
    if len(sum_counts) < 4:
        return np.array([], dtype=int)
    med = np.median(sum_counts)
    width = 1.4826 * mad(sum_counts)
    if width == 0:
        return np.array([], dtype=int)
    return np.flatnonzero(np.abs(sum_counts - med) > 3.5 * width)


def run_flowclean(
    df: pd.DataFrame,
    markers: Sequence[str],
    bin_size: float = 0.01,
    n_cell_cutoff: int = 500,
    cutoff="median",
    fc_max: float = 1.3,
    nstable: int = 5,
) -> EngineResult:
    if len(df) < 30000:
        all_idx = list(range(len(df)))
        return EngineResult(
            engine="flowclean",
            good_indices=all_idx,
            bad_indices=[],
            qc_vector=qc_series(all_idx, [], len(df)),
            details={"warning": "Too few cells for robust flowClean-style analysis"},
        )

    ordered = order_by_time(df, infer_time_channel(df))
    time_channel = infer_time_channel(ordered)
    if time_channel is None:
        all_idx = list(range(len(ordered)))
        return EngineResult(
            engine="flowclean",
            good_indices=all_idx,
            bad_indices=[],
            qc_vector=qc_series(all_idx, [], len(ordered)),
            details={"warning": "No time channel available for flowClean-style analysis"},
        )

    n_bins = int(np.ceil(1 / bin_size))
    bins = _make_bins(pd.to_numeric(ordered[time_channel], errors="coerce").fillna(0.0).to_numpy(), n_bins)
    bin_vector = np.concatenate([np.repeat(i + 1, len(chunk)) for i, chunk in enumerate(bins)]) if bins else np.array([], dtype=int)

    markers = [marker for marker in markers if marker in ordered.columns]
    pop_codes = _make_pop_codes(ordered[markers], cutoff=cutoff)
    counter_per_bin = []
    for chunk in bins:
        chunk_codes = pop_codes[chunk]
        counts = Counter(chunk_codes)
        counter_per_bin.append(counts)

    global_counts = Counter(pop_codes.tolist())
    adaptive_cutoff = min(
        max(50, int(len(ordered) * 0.0025)),
        max(50, n_cell_cutoff),
    )
    stable_populations = sorted([
        code for code, size in global_counts.items()
        if size >= adaptive_cutoff
    ])
    if len(stable_populations) < nstable:
        details = {
            "warning": "Fewer stable populations than requested",
            "stable_populations": len(stable_populations),
            "adaptive_cutoff": adaptive_cutoff,
        }
    else:
        details = {"stable_populations": len(stable_populations), "adaptive_cutoff": adaptive_cutoff}

    pop_matrix = np.array([
        [counter_per_bin[i].get(code, 0) for i in range(len(counter_per_bin))]
        for code in stable_populations
    ], dtype=float)

    if pop_matrix.size == 0:
        good = list(range(len(ordered)))
        return EngineResult(
            engine="flowclean",
            good_indices=good,
            bad_indices=[],
            qc_vector=qc_series(good, [], len(ordered)),
            details=details,
        )

    weird_bins = _flag_unlikely(pop_matrix.sum(axis=0))
    trimmed = np.delete(pop_matrix, weird_bins, axis=1) if len(weird_bins) else pop_matrix
    if trimmed.size == 0:
        flagged_trimmed = np.array([], dtype=int)
    else:
        clr = _clr(trimmed)
        norms = np.array([
            np.linalg.norm(column[column > 0], ord=max(np.sum(column > 0), 1))
            for column in clr.T
        ])
        if len(norms) == 0:
            flagged_trimmed = np.array([], dtype=int)
        else:
            median_norm = float(np.median(norms))
            width_norm = 1.4826 * mad(norms)
            threshold = median_norm + max(2.5 * width_norm, fc_max)
            flagged_trimmed = np.flatnonzero(norms > threshold)

    bad_bins = set((weird_bins + 1).tolist())
    if len(flagged_trimmed):
        kept_positions = [i for i in range(pop_matrix.shape[1]) if i not in set(weird_bins.tolist())]
        bad_bins.update(kept_positions[idx] + 1 for idx in flagged_trimmed.tolist())

    bad = np.flatnonzero(np.isin(bin_vector, list(bad_bins))).tolist()
    good = sorted(set(range(len(ordered))) - set(bad))
    details.update({"bad_bins": sorted(bad_bins), "n_bins": n_bins})
    return EngineResult(
        engine="flowclean",
        good_indices=good,
        bad_indices=sorted(bad),
        qc_vector=qc_series(good, bad, len(ordered)),
        details=details,
    )
