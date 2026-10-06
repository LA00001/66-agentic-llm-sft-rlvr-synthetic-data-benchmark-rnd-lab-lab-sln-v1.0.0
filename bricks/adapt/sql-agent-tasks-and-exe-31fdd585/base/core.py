import sqlite3

import pandas as pd

CONTRACT = "foundry.project.cybersecurity-data-exchange-route-ri-0fb020cc.v1"

_REQUIRED = {
    "customers": {"customer_id", "segment"},
    "accounts": {"account_id", "customer_id", "product", "balance"},
    "transactions": {"tx_id", "account_id", "posted_at", "amount", "category"},
}

_WINDOW_SQL = """
WITH filtered AS (
    SELECT
        t.tx_id,
        t.account_id,
        t.posted_at,
        COALESCE(t.amount, 0.0) AS amount,
        COALESCE(NULLIF(TRIM(t.category), ''), 'UNKNOWN') AS category,
        CASE WHEN t.amount IS NULL THEN 1 ELSE 0 END AS amount_was_null,
        CASE WHEN t.category IS NULL OR TRIM(t.category) = '' THEN 1 ELSE 0 END AS category_was_null
    FROM transactions AS t
    WHERE t.posted_at >= :start_date
      AND t.posted_at <= :as_of_date
      AND ABS(COALESCE(t.amount, 0.0)) >= :min_abs_amount
),
windowed AS (
    SELECT
        a.account_id,
        a.customer_id,
        c.segment,
        a.product,
        a.balance,
        f.tx_id,
        f.posted_at,
        f.amount,
        f.category,
        f.amount_was_null,
        f.category_was_null,
        ROW_NUMBER() OVER (
            PARTITION BY a.account_id
            ORDER BY ABS(f.amount) DESC, f.tx_id
        ) AS amount_rank,
        SUM(f.amount) OVER (
            PARTITION BY a.account_id
            ORDER BY f.posted_at, f.tx_id
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS rolling_3_amount
    FROM accounts AS a
    JOIN customers AS c ON c.customer_id = a.customer_id
    JOIN filtered AS f ON f.account_id = a.account_id
    WHERE (:segment IS NULL OR c.segment = :segment)
)
SELECT
    account_id, customer_id, segment, product, balance,
    tx_id, posted_at, amount, category,
    amount_was_null, category_was_null, amount_rank, rolling_3_amount
FROM windowed
ORDER BY account_id, posted_at, tx_id
"""

_MART_SQL = """
WITH filtered AS (
    SELECT
        t.tx_id,
        t.account_id,
        t.posted_at,
        COALESCE(t.amount, 0.0) AS amount,
        COALESCE(NULLIF(TRIM(t.category), ''), 'UNKNOWN') AS category,
        CASE WHEN t.amount IS NULL THEN 1 ELSE 0 END AS amount_was_null,
        CASE WHEN t.category IS NULL OR TRIM(t.category) = '' THEN 1 ELSE 0 END AS category_was_null
    FROM transactions AS t
    WHERE t.posted_at >= :start_date
      AND t.posted_at <= :as_of_date
      AND ABS(COALESCE(t.amount, 0.0)) >= :min_abs_amount
),
windowed AS (
    SELECT
        a.account_id,
        a.customer_id,
        c.segment,
        a.product,
        a.balance,
        f.tx_id,
        f.posted_at,
        f.amount,
        f.category,
        f.amount_was_null,
        f.category_was_null,
        ROW_NUMBER() OVER (
            PARTITION BY a.account_id
            ORDER BY ABS(f.amount) DESC, f.tx_id
        ) AS amount_rank,
        SUM(f.amount) OVER (
            PARTITION BY a.account_id
            ORDER BY f.posted_at, f.tx_id
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS rolling_3_amount
    FROM accounts AS a
    JOIN customers AS c ON c.customer_id = a.customer_id
    JOIN filtered AS f ON f.account_id = a.account_id
    WHERE (:segment IS NULL OR c.segment = :segment)
),
account_agg AS (
    SELECT
        account_id,
        customer_id,
        segment,
        product,
        balance,
        COUNT(*) AS txn_count,
        SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS inflow,
        SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS outflow,
        SUM(amount) AS net_flow,
        AVG(ABS(amount)) AS avg_abs_tx,
        MAX(CASE WHEN amount_rank = 1 THEN amount END) AS largest_abs_tx_signed,
        MAX(rolling_3_amount) AS max_rolling_3_amount,
        SUM(amount_was_null) AS null_amount_count,
        SUM(category_was_null) AS null_category_count
    FROM windowed
    GROUP BY account_id, customer_id, segment, product, balance
)
SELECT
    account_id, customer_id, segment, product, balance,
    txn_count, inflow, outflow, net_flow, avg_abs_tx,
    largest_abs_tx_signed, max_rolling_3_amount,
    null_amount_count, null_category_count
FROM account_agg
ORDER BY account_id
"""


def _frame(rows, name):
    if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
        raise ValueError(f"inputs.{name} must be a non-empty list of records")
    frame = pd.DataFrame(rows)
    missing = sorted(_REQUIRED[name] - set(frame.columns))
    if missing:
        raise ValueError(f"inputs.{name} missing columns: {', '.join(missing)}")
    return frame[list(sorted(_REQUIRED[name]))].copy()


def _nonempty_strings(frame, columns, label):
    for column in columns:
        values = frame[column].astype("string").str.strip()
        if values.isna().any() or values.eq("").any():
            raise ValueError(f"{label}.{column} must be non-empty")
        frame[column] = values


def _unique(frame, column, label):
    if frame[column].duplicated().any():
        raise ValueError(f"{label}.{column} must be unique")


def _date(value, name):
    if not isinstance(value, str):
        raise ValueError(f"parameters.{name} must be YYYY-MM-DD")
    parsed = pd.to_datetime(value, format="%Y-%m-%d", errors="coerce")
    if pd.isna(parsed) or parsed.strftime("%Y-%m-%d") != value:
        raise ValueError(f"parameters.{name} must be YYYY-MM-DD")
    return value


def _records(frame):
    records = []
    for row in frame.to_dict("records"):
        clean = {}
        for key, value in row.items():
            missing = pd.isna(value)
            if missing is True or (hasattr(missing, "item") and bool(missing.item())):
                clean[str(key)] = None
            elif hasattr(value, "item"):
                clean[str(key)] = value.item()
            else:
                clean[str(key)] = value
        records.append(clean)
    return records


def _profile(series):
    return {
        "dtype": str(series.dtype),
        "rows": int(len(series)),
        "nulls": int(series.isna().sum()),
        "cardinality": int(series.nunique(dropna=True)),
    }


def execute(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("inputs"), dict):
        raise ValueError("payload.inputs must be an object")

    customers = _frame(payload["inputs"].get("customers"), "customers")
    accounts = _frame(payload["inputs"].get("accounts"), "accounts")
    transactions = _frame(payload["inputs"].get("transactions"), "transactions")

    _nonempty_strings(customers, ["customer_id", "segment"], "customers")
    _nonempty_strings(accounts, ["account_id", "customer_id", "product"], "accounts")
    _nonempty_strings(transactions, ["tx_id", "account_id", "posted_at"], "transactions")
    _unique(customers, "customer_id", "customers")
    _unique(accounts, "account_id", "accounts")
    _unique(transactions, "tx_id", "transactions")

    accounts["balance"] = pd.to_numeric(accounts["balance"], errors="coerce")
    if accounts["balance"].isna().any():
        raise ValueError("accounts.balance must be numeric")
    accounts["balance"] = accounts["balance"].astype("float64")

    tx_dates = pd.to_datetime(transactions["posted_at"], format="%Y-%m-%d", errors="coerce")
    if tx_dates.isna().any():
        raise ValueError("transactions.posted_at must be YYYY-MM-DD")
    transactions["posted_at"] = tx_dates.dt.strftime("%Y-%m-%d").astype("string")
    raw_amount = transactions["amount"].copy()
    numeric_amount = pd.to_numeric(raw_amount, errors="coerce")
    invalid_amount = raw_amount.notna() & numeric_amount.isna()
    if invalid_amount.any():
        raise ValueError("transactions.amount must be numeric or null")
    transactions["amount"] = numeric_amount.astype("float64")
    transactions["category"] = transactions["category"].astype("string").str.strip()
    transactions.loc[transactions["category"].eq(""), "category"] = pd.NA

    if not set(accounts["customer_id"]).issubset(set(customers["customer_id"])):
        raise ValueError("accounts.customer_id must reference customers")
    if not set(transactions["account_id"]).issubset(set(accounts["account_id"])):
        raise ValueError("transactions.account_id must reference accounts")

    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("payload.parameters must be an object")
    start_date = _date(parameters.get("start_date"), "start_date")
    as_of_date = _date(parameters.get("as_of_date"), "as_of_date")
    if start_date > as_of_date:
        raise ValueError("parameters.start_date must not exceed as_of_date")
    min_abs_amount = parameters.get("min_abs_amount", 0.0)
    if isinstance(min_abs_amount, bool) or not isinstance(min_abs_amount, (int, float)) or min_abs_amount < 0:
        raise ValueError("parameters.min_abs_amount must be a non-negative number")
    segment = parameters.get("segment")
    if segment is not None and (not isinstance(segment, str) or not segment.strip()):
        raise ValueError("parameters.segment must be null or a non-empty string")
    if isinstance(segment, str):
        segment = segment.strip()

    segment_features = payload.get("segment_features")
    if segment_features is None:
        segment_features = [
            {"segment": value, "segment_weight": 1.0}
            for value in sorted(customers["segment"].unique().tolist())
        ]
    if not isinstance(segment_features, list) or not segment_features or not all(
        isinstance(row, dict) for row in segment_features
    ):
        raise ValueError("segment_features must be a non-empty list of records")
    ref = pd.DataFrame(segment_features)
    if not {"segment", "segment_weight"} <= set(ref.columns):
        raise ValueError("segment_features require segment and segment_weight")
    ref = ref[["segment", "segment_weight"]].copy()
    _nonempty_strings(ref, ["segment"], "segment_features")
    _unique(ref, "segment", "segment_features")
    ref["segment_weight"] = pd.to_numeric(ref["segment_weight"], errors="coerce")
    if ref["segment_weight"].isna().any() or (ref["segment_weight"] <= 0).any():
        raise ValueError("segment_features.segment_weight must be positive numeric")
    ref["segment_weight"] = ref["segment_weight"].astype("float64")

    query_params = {
        "start_date": start_date,
        "as_of_date": as_of_date,
        "min_abs_amount": float(min_abs_amount),
        "segment": segment,
    }

    connection = sqlite3.connect(":memory:")
    try:
        customers.to_sql("customers", connection, index=False, if_exists="replace")
        accounts.to_sql("accounts", connection, index=False, if_exists="replace")
        transactions.to_sql("transactions", connection, index=False, if_exists="replace")
        window_rows = pd.read_sql_query(_WINDOW_SQL, connection, params=query_params)
        mart = pd.read_sql_query(_MART_SQL, connection, params=query_params)
    finally:
        connection.close()

    if not mart.empty:
        for column in (
            "balance", "inflow", "outflow", "net_flow", "avg_abs_tx",
            "largest_abs_tx_signed", "max_rolling_3_amount"
        ):
            mart[column] = mart[column].astype("float64")
        for column in ("txn_count", "null_amount_count", "null_category_count"):
            mart[column] = mart[column].astype("int64")
        for column in ("account_id", "customer_id", "segment", "product"):
            mart[column] = mart[column].astype("string")

    if not window_rows.empty:
        for column in ("balance", "amount", "rolling_3_amount"):
            window_rows[column] = window_rows[column].astype("float64")
        for column in ("amount_was_null", "category_was_null", "amount_rank"):
            window_rows[column] = window_rows[column].astype("int64")
        for column in (
            "account_id", "customer_id", "segment", "product",
            "tx_id", "posted_at", "category"
        ):
            window_rows[column] = window_rows[column].astype("string")

    features = mart.merge(ref, on="segment", how="left", validate="many_to_one")
    if not features.empty and features["segment_weight"].isna().any():
        missing_segments = sorted(features.loc[features["segment_weight"].isna(), "segment"].unique().tolist())
        raise ValueError("segment_features missing segments: " + ", ".join(missing_segments))

    if features.empty:
        for column in ("net_flow_to_balance", "outflow_share", "weighted_activity"):
            features[column] = pd.Series(dtype="float64")
        features["is_net_outflow"] = pd.Series(dtype="int64")
    else:
        balance_denominator = features["balance"].abs().replace(0.0, pd.NA)
        activity_denominator = (features["inflow"] + features["outflow"]).replace(0.0, pd.NA)
        features["net_flow_to_balance"] = (
            features["net_flow"] / balance_denominator
        ).fillna(0.0).astype("float64")
        features["outflow_share"] = (
            features["outflow"] / activity_denominator
        ).fillna(0.0).astype("float64")
        features["weighted_activity"] = (
            features["txn_count"] * features["segment_weight"]
        ).astype("float64")
        features["is_net_outflow"] = (features["net_flow"] < 0).astype("int64")

    features = features.sort_values("account_id").reset_index(drop=True)

    if features.empty:
        segment_summary = pd.DataFrame(
            {
                "segment": pd.Series(dtype="string"),
                "account_count": pd.Series(dtype="int64"),
                "portfolio_balance": pd.Series(dtype="float64"),
                "total_net_flow": pd.Series(dtype="float64"),
                "mean_outflow_share": pd.Series(dtype="float64"),
                "weighted_activity": pd.Series(dtype="float64"),
            }
        )
    else:
        segment_summary = (
            features.groupby("segment", as_index=False, dropna=False)
            .agg(
                account_count=("account_id", "nunique"),
                portfolio_balance=("balance", "sum"),
                total_net_flow=("net_flow", "sum"),
                mean_outflow_share=("outflow_share", "mean"),
                weighted_activity=("weighted_activity", "sum"),
            )
            .sort_values("segment")
            .reset_index(drop=True)
        )
        segment_summary["segment"] = segment_summary["segment"].astype("string")
        segment_summary["account_count"] = segment_summary["account_count"].astype("int64")
        for column in (
            "portfolio_balance", "total_net_flow",
            "mean_outflow_share", "weighted_activity"
        ):
            segment_summary[column] = segment_summary[column].astype("float64")

    return {
        "contract": CONTRACT,
        "sql_engine": "sqlite3",
        "sql_features": ["CTE", "JOIN", "GROUP BY", "AGGREGATES", "WINDOW"],
        "query_parameters": query_params,
        "window_rows": _records(window_rows),
        "banking_mart": _records(mart),
        "ml_features": _records(features),
        "segment_summary": _records(segment_summary),
        "dtypes": {column: str(dtype) for column, dtype in features.dtypes.items()},
        "profile": {
            "balance": _profile(features["balance"]) if "balance" in features else {},
            "net_flow": _profile(features["net_flow"]) if "net_flow" in features else {},
            "segment": _profile(features["segment"]) if "segment" in features else {},
        },
        "metrics": {
            "sql_rows": int(len(mart)),
            "window_rows": int(len(window_rows)),
            "feature_rows": int(len(features)),
            "null_amounts_handled": int(mart["null_amount_count"].sum()) if not mart.empty else 0,
            "null_categories_handled": int(mart["null_category_count"].sum()) if not mart.empty else 0,
        },
    }
