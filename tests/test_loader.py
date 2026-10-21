"""Tests for data loading utilities."""

import pandas as pd
import pytest

from src.data.loader import describe_dataset, load_raw_csv


def test_load_raw_csv_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_raw_csv("does_not_exist.csv", data_dir=tmp_path)


def test_load_raw_csv_reads_existing_file(tmp_path):
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    df.to_csv(tmp_path / "sample.csv", index=False)

    result = load_raw_csv("sample.csv", data_dir=tmp_path)

    assert len(result) == 2
    assert list(result.columns) == ["a", "b"]


def test_describe_dataset_reports_shape_and_missing():
    df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})

    summary = describe_dataset(df)

    assert summary["rows"] == 3
    assert summary["columns"] == 2
    assert summary["missing_by_column"]["a"] == 1
    assert summary["missing_by_column"]["b"] == 0
