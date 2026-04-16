from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd


def ensure_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(column) for column in out.columns]
    return out.reset_index(drop=True)


def infer_time_channel(df: pd.DataFrame, preferred: Optional[str] = None) -> Optional[str]:
    if preferred and preferred in df.columns:
        return preferred
    exact = [column for column in df.columns if column.lower() == "time"]
    if exact:
        return exact[0]
    fuzzy = [column for column in df.columns if "time" in column.lower()]
    return fuzzy[0] if fuzzy else None


def infer_timestep(df: pd.DataFrame, metadata: Dict, time_channel: Optional[str]) -> float:
    for key, value in metadata.items():
        if "TIMESTEP" in str(key).upper():
            try:
                return float(value)
            except (ValueError, TypeError):
                pass
    if time_channel is None or time_channel not in df.columns:
        return 1.0
    values = pd.to_numeric(df[time_channel], errors="coerce").to_numpy()
    diffs = np.diff(values)
    diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
    if len(diffs) == 0:
        return 1.0
    return float(np.min(diffs))


def order_by_time(df: pd.DataFrame, time_channel: Optional[str]) -> pd.DataFrame:
    if time_channel is None or time_channel not in df.columns:
        return df.reset_index(drop=True)
    return df.sort_values(time_channel, kind="mergesort").reset_index(drop=True)


def numeric_channels(df: pd.DataFrame, exclude: Optional[Sequence[str]] = None) -> List[str]:
    exclude = set(exclude or [])
    cols = []
    for column in df.columns:
        if column in exclude:
            continue
        if pd.api.types.is_numeric_dtype(df[column]):
            cols.append(column)
    return cols


def select_channels(df: pd.DataFrame, channels: Optional[Sequence[str]] = None, exclude_patterns: Optional[Sequence[str]] = None) -> List[str]:
    if channels is None:
        channels = numeric_channels(df)
    selected = list(channels)
    if exclude_patterns:
        lowered = [pattern.lower() for pattern in exclude_patterns]
        selected = [
            channel for channel in selected
            if not any(pattern in channel.lower() for pattern in lowered)
        ]
    return selected


def choose_fluorescence_like_channels(df: pd.DataFrame, limit: int = 10, time_channel: Optional[str] = None) -> List[str]:
    preferred = []
    secondary = []
    for column in numeric_channels(df, exclude=["Original_ID"]):
        lowered = column.lower()
        if time_channel and column == time_channel:
            continue
        if "time" in lowered:
            continue
        if "fsc" in lowered or "ssc" in lowered:
            secondary.append(column)
            continue
        preferred.append(column)
    selected = preferred[:limit]
    if len(selected) < limit:
        selected.extend(secondary[: max(0, limit - len(selected))])
    return selected


def mad(values: np.ndarray) -> float:
    median = np.median(values)
    return float(np.median(np.abs(values - median)))


def chunks_with_overlap(n_items: int, chunk_size: int, overlap: int) -> List[np.ndarray]:
    if n_items <= 0:
        return []
    starts = list(range(0, n_items, max(1, chunk_size - overlap)))
    chunks = []
    for start in starts:
        end = min(n_items, start + chunk_size)
        chunks.append(np.arange(start, end))
        if end == n_items:
            break
    return chunks


def bins_from_time(df: pd.DataFrame, time_channel: str, second_fraction: float, timestep: float) -> np.ndarray:
    values = pd.to_numeric(df[time_channel], errors="coerce").fillna(0.0).to_numpy()
    endsec = int(math.ceil(timestep * np.max(values))) if len(values) else 0
    if second_fraction <= 0:
        second_fraction = max(timestep, 1.0)
    edges = np.arange(0, endsec / timestep + (second_fraction / timestep), second_fraction / timestep)
    counts, _ = np.histogram(values, bins=edges)
    bins = np.repeat(np.arange(1, len(counts) + 1), counts)
    if len(bins) < len(df):
        bins = np.pad(bins, (0, len(df) - len(bins)), constant_values=max(len(counts), 1))
    return bins[:len(df)]


def qc_series(good_idx: Sequence[int], bad_idx: Sequence[int], n_events: int) -> pd.Series:
    values = np.linspace(1, 9000, num=n_events) if n_events else np.array([])
    qc = pd.Series(values, name="QC")
    if bad_idx:
        qc.iloc[list(bad_idx)] = np.linspace(10000, 20000, num=len(bad_idx))
    return qc


def safe_mean(values: Sequence[float]) -> float:
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return 0.0
    return float(np.mean(values))
