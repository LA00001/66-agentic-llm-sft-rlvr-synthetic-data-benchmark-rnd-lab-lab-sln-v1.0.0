from __future__ import annotations
import pandas as pd

def assess(df: pd.DataFrame) -> dict:
    duplicate_mask = df.duplicated("session_id", keep=False)
    null_rows = df[["region","device","channel","experiment"]].isna().any(axis=1)
    negative_revenue = df["revenue"].fillna(0).lt(0)
    impossible_revenue = (~df["converted"].astype(bool)) & df["revenue"].fillna(0).gt(0)
    latency_outlier = df["response_ms"].fillna(0).gt(5000)
    checks = [
        {"name":"duplicate_session_id","failed_rows":int(duplicate_mask.sum())},
        {"name":"required_dimension_null","failed_rows":int(null_rows.sum())},
        {"name":"negative_revenue","failed_rows":int(negative_revenue.sum())},
        {"name":"revenue_without_conversion","failed_rows":int(impossible_revenue.sum())},
        {"name":"latency_over_5s","failed_rows":int(latency_outlier.sum())},
    ]
    invalid = duplicate_mask | null_rows | negative_revenue | impossible_revenue
    return {"status":"PASS" if not invalid.any() else "WARN", "checks":checks, "invalid_rows":int(invalid.sum()), "valid_rows":int((~invalid).sum())}

def quarantine_invalid(df: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    duplicate_mask = df.duplicated("session_id", keep="first")
    null_rows = df[["region","device","channel","experiment"]].isna().any(axis=1)
    negative_revenue = df["revenue"].fillna(0).lt(0)
    impossible_revenue = (~df["converted"].astype(bool)) & df["revenue"].fillna(0).gt(0)
    invalid = duplicate_mask | null_rows | negative_revenue | impossible_revenue
    return df.loc[~invalid].copy(), df.loc[invalid].copy()
