from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .models import CombinedQCResult, SampleResult
from .utils import infer_time_channel, numeric_channels


def generate_reports(result: CombinedQCResult, output_dir: Path | str, max_channels: int = 6, sample_points: int = 4000) -> CombinedQCResult:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sample_pages = []
    for sample in result.samples:
        sample_dir = output_dir / _safe_name(sample.name)
        sample_dir.mkdir(parents=True, exist_ok=True)
        files = _generate_sample_report(sample, sample_dir, max_channels=max_channels, sample_points=sample_points)
        sample.report_files.update(files)
        sample_pages.append((sample, files))

    index_path = output_dir / "index.html"
    index_path.write_text(_build_index_html(sample_pages), encoding="utf-8")
    return result


def _generate_sample_report(sample: SampleResult, sample_dir: Path, max_channels: int, sample_points: int) -> dict:
    files = {}
    engine_plot = sample_dir / "engine_summary.png"
    _plot_engine_summary(sample, engine_plot)
    files["engine_summary_png"] = engine_plot.name

    channels_plot = sample_dir / "channels_overview.png"
    _plot_channel_overview(sample, channels_plot, max_channels=max_channels, sample_points=sample_points)
    files["channels_overview_png"] = channels_plot.name

    time_channel = infer_time_channel(sample.preprocessed)
    if time_channel:
        time_plot = sample_dir / "time_overview.png"
        _plot_time_overview(sample, time_channel, time_plot, sample_points=sample_points)
        files["time_overview_png"] = time_plot.name

    sample_html = sample_dir / "index.html"
    sample_html.write_text(_build_sample_html(sample, files), encoding="utf-8")
    files["html"] = sample_html.name
    return files


def _plot_engine_summary(sample: SampleResult, output_path: Path) -> None:
    labels = []
    values = []
    for engine_name, engine_res in sample.engine_results.items():
        labels.append(engine_name)
        values.append(engine_res.percent_removed)
    labels.append("final")
    final_removed = 0.0 if len(sample.preprocessed) == 0 else 100.0 * len(sample.final_bad_indices) / len(sample.preprocessed)
    values.append(final_removed)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = ["#4C78A8", "#F58518", "#54A24B", "#E45756"][:len(labels)]
    ax.bar(labels, values, color=colors)
    ax.set_ylabel("Percent removed")
    ax.set_ylim(0, max(100, max(values) * 1.15 if values else 100))
    ax.set_title("Removal summary")
    for i, value in enumerate(values):
        ax.text(i, value + 1, "{0:.1f}%".format(value), ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_channel_overview(sample: SampleResult, output_path: Path, max_channels: int, sample_points: int) -> None:
    df = sample.preprocessed
    channels = [column for column in numeric_channels(df, exclude=["Original_ID"]) if column.lower() != "time"][:max_channels]
    if not channels:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, "No numeric channels available", ha="center", va="center")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(output_path, dpi=180)
        plt.close(fig)
        return

    sample_idx = _sample_indices(len(df), sample_points)
    good_set = set(sample.final_good_indices)
    kept_mask = np.array([idx in good_set for idx in sample_idx], dtype=bool)

    ncols = 2
    nrows = int(np.ceil(len(channels) / float(ncols)))
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(12, max(3 * nrows, 4)), squeeze=False)
    axes_flat = axes.ravel()

    for ax, channel in zip(axes_flat, channels):
        values = pd.to_numeric(df.iloc[sample_idx][channel], errors="coerce").to_numpy(dtype=float)
        x = np.asarray(sample_idx)
        ax.scatter(x[kept_mask], values[kept_mask], s=4, c="#2E8B57", alpha=0.5, label="kept")
        ax.scatter(x[~kept_mask], values[~kept_mask], s=4, c="#D1495B", alpha=0.5, label="removed")
        ax.set_title(channel)
        ax.set_xlabel("Event index")
        ax.set_ylabel("Signal")

    for ax in axes_flat[len(channels):]:
        ax.axis("off")

    handles, labels = axes_flat[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper right")
    fig.suptitle("Channel overview", y=0.995)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_time_overview(sample: SampleResult, time_channel: str, output_path: Path, sample_points: int) -> None:
    df = sample.preprocessed
    sample_idx = _sample_indices(len(df), sample_points)
    x = np.asarray(sample_idx)
    time_values = pd.to_numeric(df.iloc[sample_idx][time_channel], errors="coerce").to_numpy(dtype=float)
    good_set = set(sample.final_good_indices)
    kept_mask = np.array([idx in good_set for idx in sample_idx], dtype=bool)

    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(10, 7))
    axes[0].scatter(x[kept_mask], time_values[kept_mask], s=5, c="#2E8B57", alpha=0.5, label="kept")
    axes[0].scatter(x[~kept_mask], time_values[~kept_mask], s=5, c="#D1495B", alpha=0.5, label="removed")
    axes[0].set_title("Time channel")
    axes[0].set_xlabel("Event index")
    axes[0].set_ylabel(time_channel)
    axes[0].legend(loc="best")

    full_time = pd.to_numeric(df[time_channel], errors="coerce").to_numpy(dtype=float)
    axes[1].hist(full_time, bins=min(100, max(10, len(full_time) // 200)), color="#4C78A8", alpha=0.8)
    axes[1].set_title("Time histogram")
    axes[1].set_xlabel(time_channel)
    axes[1].set_ylabel("Count")

    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _sample_indices(n: int, k: int) -> List[int]:
    if n <= k:
        return list(range(n))
    return np.linspace(0, n - 1, num=k, dtype=int).tolist()


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _build_index_html(sample_pages: Iterable[tuple[SampleResult, dict]]) -> str:
    items = []
    for sample, files in sample_pages:
        items.append(
            "<tr>"
            "<td>{name}</td>"
            "<td>{raw}</td>"
            "<td>{prep}</td>"
            "<td>{final}</td>"
            "<td><a href=\"{folder}/{html}\">open report</a></td>"
            "</tr>".format(
                name=sample.name,
                raw=len(sample.raw),
                prep=len(sample.preprocessed),
                final=len(sample.final),
                folder=_safe_name(sample.name),
                html=files["html"],
            )
        )
    rows = "\n".join(items)
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>DurDur Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #18212b; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #d7dee5; padding: 10px 12px; text-align: left; }}
    th {{ background: #f4f7fa; }}
  </style>
</head>
<body>
  <h1>DurDur QC Report</h1>
  <table>
    <thead>
      <tr><th>Sample</th><th>Raw events</th><th>Preprocessed events</th><th>Final events</th><th>Report</th></tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>""".format(rows=rows)


def _build_sample_html(sample: SampleResult, files: dict) -> str:
    engine_rows = []
    for name, result in sample.engine_results.items():
        engine_rows.append(
            "<tr><td>{name}</td><td>{removed}</td><td>{percent:.2f}%</td></tr>".format(
                name=name,
                removed=len(result.bad_indices),
                percent=result.percent_removed,
            )
        )
    engine_rows_html = "\n".join(engine_rows)

    preprocessing_html = ""
    if sample.preprocessing:
        rows = "".join(
            "<tr><td>{key}</td><td>{value}</td></tr>".format(key=key, value=info.get("removed", 0))
            for key, info in sample.preprocessing.items()
        )
        preprocessing_html = (
            "<h2>Preprocessing</h2>"
            "<table><thead><tr><th>Step</th><th>Removed</th></tr></thead><tbody>{rows}</tbody></table>".format(rows=rows)
        )

    recommendation = sample.recommendation or {}
    rec_html = ""
    if recommendation:
        warnings = recommendation.get("warnings", [])
        notes = recommendation.get("notes", [])
        warnings_html = ""
        notes_html = ""
        if warnings:
            warnings_html = "<h3>Warnings</h3><ul>{0}</ul>".format(
                "".join("<li>{0}</li>".format(item) for item in warnings)
            )
        if notes:
            notes_html = "<h3>Notes</h3><ul>{0}</ul>".format(
                "".join("<li>{0}</li>".format(item) for item in notes)
            )
        rec_html = (
            "<h2>Recommendation</h2>"
            "<p><strong>Recommended engine:</strong> {engine}</p>"
            "<p>{summary}</p>"
            "{warnings}{notes}"
        ).format(
            engine=recommendation.get("recommended_engine", "n/a"),
            summary=recommendation.get("summary", ""),
            warnings=warnings_html,
            notes=notes_html,
        )

    time_section = ""
    if "time_overview_png" in files:
        time_section = "<h2>Time</h2><img src=\"{0}\" alt=\"Time overview\">".format(files["time_overview_png"])

    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>DurDur Report - {name}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #18212b; }}
    h1, h2 {{ margin-top: 28px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; margin: 20px 0 24px; }}
    .metric {{ background: #f4f7fa; border: 1px solid #d7dee5; border-radius: 10px; padding: 14px; }}
    .metric .value {{ font-size: 24px; font-weight: 700; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
    th, td {{ border-bottom: 1px solid #d7dee5; padding: 10px 12px; text-align: left; }}
    th {{ background: #f4f7fa; }}
    img {{ max-width: 100%%; border: 1px solid #d7dee5; border-radius: 10px; margin-top: 10px; }}
    .muted {{ color: #5f6b76; }}
  </style>
</head>
<body>
  <p><a href="../index.html">Back to report index</a></p>
  <h1>{name}</h1>
  <p class="muted">Source: {source}</p>

  <div class="metrics">
    <div class="metric"><div class="label">Raw</div><div class="value">{raw}</div></div>
    <div class="metric"><div class="label">Preprocessed</div><div class="value">{prep}</div></div>
    <div class="metric"><div class="label">Final</div><div class="value">{final}</div></div>
    <div class="metric"><div class="label">Removed</div><div class="value">{removed}</div></div>
  </div>

  {preprocessing}
  {recommendation}

  <h2>Engine Summary</h2>
  <table>
    <thead><tr><th>Engine</th><th>Removed events</th><th>Percent removed</th></tr></thead>
    <tbody>{engine_rows}</tbody>
  </table>
  <img src="{engine_summary_png}" alt="Engine summary">

  <h2>Channel Overview</h2>
  <img src="{channels_overview_png}" alt="Channel overview">

  {time_section}
</body>
</html>""".format(
        name=sample.name,
        source="dataframe" if sample.source_path is None else sample.source_path,
        raw=len(sample.raw),
        prep=len(sample.preprocessed),
        final=len(sample.final),
        removed=len(sample.final_bad_indices),
        preprocessing=preprocessing_html,
        recommendation=rec_html,
        engine_rows=engine_rows_html,
        engine_summary_png=files["engine_summary_png"],
        channels_overview_png=files["channels_overview_png"],
        time_section=time_section,
    )
