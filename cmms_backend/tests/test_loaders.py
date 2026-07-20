"""
Test 9 — Seed loaders (Fix #6).
Verifies that _val() helper correctly reads values from a pandas Series
regardless of the DataFrame's index type (default, reset, string-labelled).
"""
import pandas as pd
import pytest

from app.db.seed.loaders import _val, _normalise_columns


def _make_df(data: dict, index=None) -> pd.DataFrame:
    df = pd.DataFrame([data])
    if index is not None:
        df.index = [index]
    return _normalise_columns(df)


def test_val_default_range_index():
    df = _make_df({"Asset Name": "Machine A", "Category": "Knitting"})
    for _, row in df.iterrows():
        assert _val(row, "asset_name") == "Machine A"
        assert _val(row, "category") == "Knitting"


def test_val_non_default_index():
    """FIX #6: must work even when the DataFrame has a non-zero start index."""
    df = _make_df({"Asset Name": "Machine B"}, index=99)
    for _, row in df.iterrows():
        assert _val(row, "asset_name") == "Machine B"


def test_val_candidate_fallback():
    """First matching candidate should be returned."""
    df = _make_df({"name": "Machine C"})
    for _, row in df.iterrows():
        assert _val(row, "asset_name", "name", "asset") == "Machine C"


def test_val_missing_column_returns_none():
    df = _make_df({"name": "Machine D"})
    for _, row in df.iterrows():
        assert _val(row, "nonexistent_col") is None


def test_val_nan_returns_none():
    import numpy as np
    df = _make_df({"asset_name": float("nan")})
    for _, row in df.iterrows():
        assert _val(row, "asset_name") is None


def test_normalise_columns_strips_spaces():
    df = pd.DataFrame([{"Asset Name ": "X", " Category": "Y"}])
    df = _normalise_columns(df)
    assert "asset_name" in df.columns
    assert "category" in df.columns
