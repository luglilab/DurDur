from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union

import pandas as pd

InputType = Union[str, Path, pd.DataFrame]


def load_samples(data: Union[InputType, Iterable[InputType]]) -> List[Tuple[str, Optional[Path], pd.DataFrame, dict]]:
    if isinstance(data, pd.DataFrame):
        return [("dataframe", None, data.copy(), {})]
    if isinstance(data, (str, Path)):
        return [_load_one(Path(data))]

    samples = []
    for item in data:
        if isinstance(item, pd.DataFrame):
            samples.append(("dataframe", None, item.copy(), {}))
        else:
            samples.append(_load_one(Path(item)))
    return samples


def _load_one(path: Path) -> Tuple[str, Optional[Path], pd.DataFrame, dict]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return path.stem, path, pd.read_csv(path), {}
    if suffix in {".tsv", ".txt"}:
        return path.stem, path, pd.read_csv(path, sep="\t"), {}
    if suffix == ".fcs":
        try:
            from fcsparser import parse
        except ImportError as exc:
            raise ImportError(
                "Reading .fcs files requires the optional dependency 'fcsparser'. "
                "Install it with: pip install fcsparser"
            ) from exc
        meta, df = parse(str(path), reformat_meta=True)
        return path.stem, path, df.copy(), meta
    raise ValueError("Unsupported input type: {0}".format(path))
