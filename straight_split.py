from typing import List

import geopandas as gpd
import pandas as pd


def _choose_axis(df: pd.DataFrame) -> str:
    x_span = float(df["x"].max() - df["x"].min()) if len(df) else 0.0
    y_span = float(df["y"].max() - df["y"].min()) if len(df) else 0.0
    return "x" if x_span >= y_span else "y"


def _split_indices_balanced(df: pd.DataFrame, k: int, weight_col: str) -> List[List[int]]:
    if k <= 1 or len(df) <= 1:
        return [df.index.tolist()]

    if len(df) <= k:
        return [[idx] for idx in df.index.tolist()]

    left_k = k // 2
    right_k = k - left_k

    axis = _choose_axis(df)
    ordered = df.sort_values([axis, weight_col, "id"]).copy()

    total_weight = float(ordered[weight_col].sum())
    if total_weight <= 0:
        split_pos = max(1, min(len(ordered) - 1, len(ordered) * left_k // k))
    else:
        target_left_weight = total_weight * left_k / k
        cum = ordered[weight_col].cumsum().astype(float)

        best_pos = None
        best_score = None
        for pos in range(1, len(ordered)):
            left_weight = float(cum.iloc[pos - 1])
            score = abs(left_weight - target_left_weight)
            if best_score is None or score < best_score:
                best_score = score
                best_pos = pos

        split_pos = best_pos or max(1, len(ordered) // 2)

    left_df = ordered.iloc[:split_pos].copy()
    right_df = ordered.iloc[split_pos:].copy()

    if left_df.empty or right_df.empty:
        split_pos = max(1, min(len(ordered) - 1, len(ordered) // 2))
        left_df = ordered.iloc[:split_pos].copy()
        right_df = ordered.iloc[split_pos:].copy()

    return (
        _split_indices_balanced(left_df, left_k, weight_col)
        + _split_indices_balanced(right_df, right_k, weight_col)
    )


def split_indices_straight(gdf: gpd.GeoDataFrame, split_count: int) -> List[List[int]]:
    if gdf.empty:
        return []

    split_count = max(1, min(int(split_count), len(gdf)))
    base_df = gdf[["id", "population", "pop65", "x", "y"]].copy()
    base_df["balance_value"] = base_df["pop65"]
    return _split_indices_balanced(base_df, split_count, "balance_value")
