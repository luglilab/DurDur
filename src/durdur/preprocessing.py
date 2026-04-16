from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .utils import mad, select_channels


def remove_margins(
    df: pd.DataFrame,
    channels: Optional[Sequence[str]] = None,
    channel_specifications: Optional[Dict[str, Tuple[float, float]]] = None,
    remove_min: Optional[Sequence[str]] = None,
    remove_max: Optional[Sequence[str]] = None,
    keep_original_id: bool = True,
):
    frame = df.copy().reset_index(drop=True)
    if keep_original_id and "Original_ID" not in frame.columns:
        frame["Original_ID"] = np.arange(len(frame))

    channel_specifications = channel_specifications or {}
    channels = list(channels or select_channels(frame, exclude_patterns=["time", "original_id"]))
    remove_min = set(remove_min or channels)
    remove_max = set(remove_max or channels)

    selection = np.ones(len(frame), dtype=bool)
    margin_matrix = {}

    for channel in channels:
        values = pd.to_numeric(frame[channel], errors="coerce").to_numpy(dtype=float)
        min_range = float(np.nanmin(values))
        max_range = float(np.nanmax(values))
        if channel in channel_specifications:
            min_range, max_range = channel_specifications[channel]

        lower_count = 0
        upper_count = 0
        if channel in remove_min:
            min_events = values <= max(min(min_range, 0.0), float(np.nanmin(values)))
            lower_count = int(np.sum(min_events))
            selection &= ~min_events
        if channel in remove_max:
            max_events = values >= min(max_range, float(np.nanmax(values)))
            upper_count = int(np.sum(max_events))
            selection &= ~max_events
        margin_matrix[channel] = {"min": lower_count, "max": upper_count}

    removed = np.flatnonzero(~selection).tolist()
    kept = frame.loc[selection].reset_index(drop=True)
    return {
        "frame": kept,
        "indices_margins": removed,
        "margin_matrix": margin_matrix,
    }


def remove_doublets(
    df: pd.DataFrame,
    channel1: str = "FSC-A",
    channel2: str = "FSC-H",
    nmad: float = 4.0,
    b: float = 0.0,
    keep_original_id: bool = True,
):
    frame = df.copy().reset_index(drop=True)
    if keep_original_id and "Original_ID" not in frame.columns:
        frame["Original_ID"] = np.arange(len(frame))

    ratio = pd.to_numeric(frame[channel1], errors="coerce").to_numpy(dtype=float) / (
        1e-10 + pd.to_numeric(frame[channel2], errors="coerce").to_numpy(dtype=float) + b
    )
    center = float(np.median(ratio))
    width = 1.4826 * mad(ratio)
    selection = ratio < (center + nmad * width)
    removed = np.flatnonzero(~selection).tolist()
    kept = frame.loc[selection].reset_index(drop=True)
    return {
        "frame": kept,
        "indices_doublets": removed,
        "median_ratio": center,
        "width": width,
    }
