# DurDur Tutorial

This tutorial walks through a practical `DurDur` workflow from installation to report review.

## 1. Set Up The Environment

Open a terminal and move into the repository:

```bash
cd /Users/simonepuccio/Documents/GitHub/DurDur
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the package:

```bash
pip install --upgrade pip
pip install -e .
pip install fcsparser
```

## 2. Run A First QC Analysis

Use your test file:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs \
  --engine combined \
  --combination-strategy majority \
  --report-dir DurDur_report
```

What this does:

- reads the FCS file
- runs `flowai`
- runs `flowclean`
- runs `peacoqc`
- merges results using majority vote
- creates a report directory
- prints a JSON summary in the terminal

## 3. Open The Report

After the run, open:

```bash
DurDur_report/index.html
```

Inside the report you will find:

- a sample summary
- engine removal rates
- recommendation text
- channel overview plots
- time overview plot if available

## 4. Understand The Engines

### `flowai`

Use this when you want a practical stability-oriented QC pass based on:

- flow rate anomalies
- signal shifts
- margin-like problems

Typical command:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs --engine flowai --report-dir report_flowai
```

### `flowclean`

Use this when you want a population-composition style check over time.

Typical command:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs --engine flowclean --report-dir report_flowclean
```

This approach tends to make more sense on larger files.

### `peacoqc`

Use this when you want a peak-driven signal stability check.

Typical command:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs --engine peacoqc --report-dir report_peacoqc
```

This can be aggressive on very small files, so always inspect the recommendation section.

## 5. Compare Combination Strategies

### Majority

Recommended starting point:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs \
  --engine combined \
  --combination-strategy majority \
  --report-dir report_majority
```

### Intersection

Strict mode. Keeps only events accepted by all engines:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs \
  --engine combined \
  --combination-strategy intersection \
  --report-dir report_intersection
```

### Union

Loose mode. Keeps events accepted by any engine:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs \
  --engine combined \
  --combination-strategy union \
  --report-dir report_union
```

## 6. Use Preprocessing

If you want to remove margins and doublets before QC:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs \
  --engine combined \
  --preprocess-margins \
  --preprocess-doublets \
  --report-dir report_preprocessed
```

This can be useful if:

- scatter channels contain obvious edge events
- the file has likely doublets
- you want a cleaner input for the QC engines

## 7. Save The JSON Summary

You can save the machine-readable output:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs \
  --engine combined \
  --report-dir report_json \
  --summary-json report_json/summary.json
```

This is useful for:

- pipelines
- batch processing
- downstream dashboards

## 8. Use DurDur In Python

Here is the same workflow from Python:

```python
from durdur import run_qc

result = run_qc(
    "/Users/simonepuccio/Desktop/Test.fcs",
    engine="combined",
    combination_strategy="majority",
    report_dir="DurDur_report_py",
)

print(result.summary())

sample = result.samples[0]
print(sample.recommendation)
clean_df = sample.final
```

## 9. Run On Tabular Data

You can also use CSV files:

```bash
durdur run example.csv --engine flowai --report-dir csv_report
```

Or from Python:

```python
import pandas as pd
from durdur import run_qc

df = pd.read_csv("example.csv")
res = run_qc(df, engine="flowai")
```

## 10. Interpret The Recommendation Block

The recommendation block is meant to help when engines disagree.

Look at:

- `recommended_engine`
- `warnings`
- `notes`

Examples of warnings:

- sample too small
- one engine removed almost all cells
- combined result is too strict

Use that block to decide whether:

- the combined output is acceptable
- one specific engine should be trusted more
- the file should be reviewed manually

## 11. Suggested Workflow For Real Use

For routine use, this is a sensible order:

1. Start with `combined` and `majority`.
2. Read the recommendation section.
3. If the sample is small, compare with `flowai` alone.
4. If removals are extreme, inspect the plots.
5. If needed, rerun with preprocessing enabled.

## 12. Example Session

Minimal:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs --engine flowai
```

Recommended:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs \
  --engine combined \
  --combination-strategy majority \
  --report-dir DurDur_report \
  --summary-json DurDur_report/summary.json
```

Strict:

```bash
durdur run /Users/simonepuccio/Desktop/Test.fcs \
  --engine combined \
  --combination-strategy intersection \
  --report-dir DurDur_report_strict
```

## 13. Where To Go Next

Useful reference files:

- [HELP.md](/Users/simonepuccio/Documents/GitHub/DurDur/HELP.md)
- [README.md](/Users/simonepuccio/Documents/GitHub/DurDur/README.md)
- [src/durdur/api.py](/Users/simonepuccio/Documents/GitHub/DurDur/src/durdur/api.py:1)
- [src/durdur/reports.py](/Users/simonepuccio/Documents/GitHub/DurDur/src/durdur/reports.py:1)
