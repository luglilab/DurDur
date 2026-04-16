from __future__ import annotations

import numpy as np
import pandas as pd

from durdur import run_qc


def test_combined_smoke():
    n = 40000
    df = pd.DataFrame(
        {
            "Time": np.arange(n),
            "FSC-A": np.linspace(100, 1000, n),
            "FSC-H": np.linspace(90, 980, n),
            "CD3": np.r_[np.full(15000, 100.0), np.full(10000, 3000.0), np.full(15000, 120.0)],
            "CD19": np.r_[np.full(20000, 200.0), np.full(5000, 3500.0), np.full(15000, 220.0)],
            "CD45": np.r_[np.full(10000, 500.0), np.full(15000, 520.0), np.full(15000, 5000.0)],
        }
    )
    result = run_qc(df, engine="combined")
    assert len(result.samples) == 1
    assert len(result.samples[0].engine_results) == 3
