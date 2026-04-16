# DurDur Help

`DurDur` is a Python package for flow cytometry quality control inspired by:

- `flowAI`
- `flowClean`
- `PeacoQC`

It supports:

- `.fcs` input files
- tabular input files such as `.csv`, `.tsv`, `.txt`
- in-memory pandas data frames

## Main Concepts

`DurDur` provides three QC engines:

- `flowai`
  Focuses on flow rate, signal stability, and dynamic range style checks.
- `flowclean`
  Uses a composition-based stability approach inspired by population changes over time.
- `peacoqc`
  Uses peak-based signal stability logic with MAD and isolation-style filtering.

It also provides a `combined` mode that runs all engines and merges their decisions.

## Installation

From the repository root:

```bash
cd /Users/simonepuccio/Documents/GitHub/DurDur

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -e .
```

For `.fcs` support:

```bash
pip install fcsparser
```

## Command Line Usage

Run one engine:

```bash
durdur run sample.fcs --engine flowai
```

Run all engines together:

```bash
durdur run sample.fcs --engine combined --combination-strategy majority
```

Generate a report:

```bash
durdur run sample.fcs --engine combined --report-dir DurDur_report
```

Add preprocessing:

```bash
durdur run sample.fcs \
  --engine combined \
  --preprocess-margins \
  --preprocess-doublets \
  --report-dir DurDur_report
```

Write the summary to JSON:

```bash
durdur run sample.fcs \
  --engine combined \
  --report-dir DurDur_report \
  --summary-json result_summary.json
```

## Python Usage

```python
from durdur import run_qc

result = run_qc(
    "sample.fcs",
    engine="combined",
    combination_strategy="majority",
    report_dir="DurDur_report",
)

print(result.summary())

sample = result.samples[0]
cleaned_df = sample.final
```

## Combination Strategies

When `engine="combined"`, you can choose how the engines are merged:

- `majority`
  Keep events accepted by most engines. This is the default.
- `intersection`
  Keep only events accepted by all engines. This is the strictest option.
- `union`
  Keep events accepted by any engine. This is the loosest option.

Example:

```bash
durdur run sample.fcs --engine combined --combination-strategy intersection
```

## Reports

If `--report-dir` is provided, `DurDur` creates:

- a top-level `index.html`
- one subfolder per sample
- `engine_summary.png`
- `channels_overview.png`
- `time_overview.png` when a time channel is found
- a per-sample HTML summary page

## Outputs

The CLI prints a JSON summary with:

- sample name
- source path
- number of raw events
- number of preprocessed events
- number of final kept events
- number of removed events
- per-engine removal summaries
- recommendation section
- generated report files

## Recommendation Section

Each sample summary may include:

- `recommended_engine`
- `summary`
- `warnings`
- `notes`

This is useful for:

- very small samples
- cases where one engine removes almost everything
- cases where the combined result is much stricter than expected

## Preprocessing Helpers

You can also use preprocessing directly in Python:

```python
from durdur import remove_doublets, remove_margins

margin_result = remove_margins(df)
doublet_result = remove_doublets(df)
```

These return dictionaries containing:

- a filtered frame
- removed indices
- method-specific summary values

## Common Issues

### `ImportError: Reading .fcs files requires the optional dependency 'fcsparser'`

Install:

```bash
pip install fcsparser
```

### `matplotlib` or font warnings during report generation

These usually do not block report creation. In restricted environments you can set:

```bash
MPLCONFIGDIR=/tmp
```

Example:

```bash
MPLCONFIGDIR=/tmp durdur run sample.fcs --engine combined --report-dir DurDur_report
```

### Very small files give extreme results

This can happen because the original methods were designed with larger event counts in mind. In those cases:

- prefer reading the recommendation section
- compare `flowai` vs `combined`
- avoid `intersection` mode unless you want a very strict filter

## File Locations

Main package:

- [src/durdur/api.py](/Users/simonepuccio/Documents/GitHub/DurDur/src/durdur/api.py:1)
- [src/durdur/cli.py](/Users/simonepuccio/Documents/GitHub/DurDur/src/durdur/cli.py:1)
- [src/durdur/reports.py](/Users/simonepuccio/Documents/GitHub/DurDur/src/durdur/reports.py:1)

Engines:

- [flowAI engine](/Users/simonepuccio/Documents/GitHub/DurDur/src/durdur/engines/flowai_engine.py:1)
- [flowClean engine](/Users/simonepuccio/Documents/GitHub/DurDur/src/durdur/engines/flowclean_engine.py:1)
- [PeacoQC engine](/Users/simonepuccio/Documents/GitHub/DurDur/src/durdur/engines/peacoqc_engine.py:1)
