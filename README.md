# DurDur

`DurDur` is a unified Python package that combines ideas from three R/Bioconductor
quality-control tools for flow cytometry:

- `flowAI`
- `flowClean`
- `PeacoQC`

Instead of exposing three unrelated ports, `DurDur` provides:

- shared FCS/DataFrame loading
- shared preprocessing helpers
- a common result object
- engine-specific workflows for:
  - `flowai`
  - `flowclean`
  - `peacoqc`
- a `combined` workflow that can run multiple engines on the same sample

## Install

```bash
cd /Users/simonepuccio/Documents/GitHub/DurDur
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Optional dependency for reading `.fcs` files:

```bash
pip install fcsparser
```

## Python usage

```python
from durdur import run_qc

res = run_qc("sample.fcs", engine="combined")
print(res.summary())

res = run_qc("sample.fcs", engine="combined", report_dir="DurDur_report")
```

## CLI usage

```bash
durdur run sample.fcs --engine combined --combination-strategy majority
durdur run sample.fcs --engine combined --report-dir DurDur_report
```

## Current scope

This package implements the main automatic workflows, shared preprocessing,
and static HTML/PNG reporting. It does not attempt to reproduce the original R
plotting stacks or exact Bioconductor object semantics.
