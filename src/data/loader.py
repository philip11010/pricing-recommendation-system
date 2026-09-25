"""
Data acquisition and loading.

Responsible for reading raw datasets from disk into memory. Keeping loading
separate from preprocessing allows the same preprocessing pipeline to be
applied regardless of data source (platform dataset or Inside Airbnb proxy).
"""

from pathlib import Path

import pandas as pd

from src.config import RAW_DATA_DIR


def load_raw_csv(filename: str, data_dir: Path = RAW_DATA_DIR) -> pd.DataFrame:
    """
    Load a raw CSV file from the raw data directory.

    Args:
        filename: Name of the CSV file, e.g. "listings.csv".
        data_dir: Directory to read from. Defaults to the configured raw
            data directory.

    Returns:
        The loaded DataFrame.

    Raises:
        FileNotFoundError: If the file does not exist at the expected path.
    """
    path = data_dir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Expected data file not found at {path}. "
            f"Place the raw dataset in {data_dir} before running."
        )
    return pd.read_csv(path)


def describe_dataset(df: pd.DataFrame) -> dict:
    """
    Produce a summary of dataset shape and completeness.

    Used during exploratory analysis to document row count, column count,
    and missing value rates, as required by the data quality discussion in
    Section 4.2.3.
    """
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "missing_by_column": df.isna().sum().to_dict(),
        "missing_rate_overall": float(df.isna().sum().sum() / df.size),
        "dtypes": df.dtypes.astype(str).to_dict(),
    }
