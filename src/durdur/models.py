from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class EngineResult:
    engine: str
    good_indices: List[int]
    bad_indices: List[int]
    qc_vector: pd.Series
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def percent_removed(self) -> float:
        total = len(self.good_indices) + len(self.bad_indices)
        return 0.0 if total == 0 else 100.0 * len(self.bad_indices) / total


@dataclass
class SampleResult:
    name: str
    source_path: Optional[Path]
    raw: pd.DataFrame
    preprocessed: pd.DataFrame
    final: pd.DataFrame
    final_good_indices: List[int]
    final_bad_indices: List[int]
    preprocessing: Dict[str, Any]
    engine_results: Dict[str, EngineResult]
    recommendation: Dict[str, Any] = field(default_factory=dict)
    report_files: Dict[str, str] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source_path": None if self.source_path is None else str(self.source_path),
            "events_raw": len(self.raw),
            "events_preprocessed": len(self.preprocessed),
            "events_final": len(self.final),
            "events_removed_final": len(self.final_bad_indices),
            "preprocessing": self.preprocessing,
            "recommendation": self.recommendation,
            "report_files": self.report_files,
            "engines": {
                key: {
                    "removed": len(value.bad_indices),
                    "percent_removed": round(value.percent_removed, 3),
                }
                for key, value in self.engine_results.items()
            },
        }


@dataclass
class CombinedQCResult:
    samples: List[SampleResult]

    def __iter__(self):
        return iter(self.samples)

    def __len__(self) -> int:
        return len(self.samples)

    def summary(self) -> List[Dict[str, Any]]:
        return [sample.summary() for sample in self.samples]
