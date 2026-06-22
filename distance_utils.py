import math
from typing import List, Tuple

import numpy as np
import streamlit as st
from sqlalchemy import text

from config import (
    ROUTE_COSTING,
    ROUTE_MANEUVER_PENALTY,
    ROUTE_MATRIX_TABLE,
    ROUTE_SHORT_PATH,
    ROUTE_TOP_SPEED,
    ROUTE_USE_LIVING_STREETS,
)
from data_loader import get_db_engine


def get_straight_dist(lon1, lat1, lon2, lat2) -> float:
    try:
        lon1, lat1, lon2, lat2 = map(float, [lon1, lat1, lon2, lat2])
        rad_lat1, rad_lon1 = math.radians(lat1), math.radians(lon1)
        rad_lat2, rad_lon2 = math.radians(lat2), math.radians(lon2)
        lat_avg = (rad_lat1 + rad_lat2) / 2.0
        lat_diff = rad_lat1 - rad_lat2
        lon_diff = rad_lon1 - rad_lon2
        a, e2 = 6378137.0, 0.006694379990141317
        w = math.sqrt(1 - e2 * math.sin(lat_avg) ** 2)
        m = a * (1 - e2) / (w ** 3)
        n = a / w
        dist = math.sqrt((lat_diff * m) ** 2 + (lon_diff * n * math.cos(lat_avg)) ** 2)
        return round(dist / 1000, 3)
    except Exception:
        return 0.0


def build_straight_distance_matrix(points: List[Tuple[float, float]]) -> np.ndarray:
    n = len(points)
    mat = np.zeros((n, n), dtype=float)
    for i in range(n):
        lon1, lat1 = points[i]
        for j in range(i + 1, n):
            lon2, lat2 = points[j]
            d = get_straight_dist(lon1, lat1, lon2, lat2)
            mat[i, j] = d
            mat[j, i] = d
    return mat


@st.cache_data(show_spinner=False)
def load_route_distance_matrix_from_db(point_records: Tuple[Tuple[int, float, float], ...]) -> np.ndarray:
    ids = [int(pid) for pid, _, _ in point_records]
    n = len(ids)
    if n == 0:
        return np.zeros((0, 0), dtype=float)

    id_to_idx = {pid: i for i, pid in enumerate(ids)}
    mat = np.full((n, n), np.inf, dtype=float)
    np.fill_diagonal(mat, 0.0)

    sql = text(f"""
        SELECT source_id, target_id, distance_km
        FROM {ROUTE_MATRIX_TABLE}
        WHERE source_id = ANY(:ids)
          AND target_id = ANY(:ids)
          AND costing = :costing
          AND top_speed = :top_speed
          AND maneuver_penalty = :maneuver_penalty
          AND short_path = :short_path
          AND use_living_streets = :use_living_streets
    """)

    with get_db_engine().connect() as conn:
        rows = conn.execute(
            sql,
            {
                "ids": ids,
                "costing": ROUTE_COSTING,
                "top_speed": ROUTE_TOP_SPEED,
                "maneuver_penalty": ROUTE_MANEUVER_PENALTY,
                "short_path": ROUTE_SHORT_PATH,
                "use_living_streets": ROUTE_USE_LIVING_STREETS,
            },
        ).fetchall()

    for source_id, target_id, distance_km in rows:
        i = id_to_idx.get(int(source_id))
        j = id_to_idx.get(int(target_id))
        if i is not None and j is not None and distance_km is not None:
            mat[i, j] = float(distance_km)

    return mat


def sanitize_distance_matrix(distance_mat: np.ndarray) -> np.ndarray:
    mat = np.array(distance_mat, dtype=float, copy=True)
    n = mat.shape[0]
    if n == 0:
        return mat

    finite_vals = mat[np.isfinite(mat) & (mat > 0)]
    fallback = float(np.median(finite_vals)) if finite_vals.size else 1.0
    very_large = fallback * 50.0

    for i in range(n):
        mat[i, i] = 0.0
        for j in range(i + 1, n):
            a = mat[i, j]
            b = mat[j, i]
            if np.isfinite(a) and np.isfinite(b):
                v = (a + b) / 2.0
            elif np.isfinite(a):
                v = a
            elif np.isfinite(b):
                v = b
            else:
                v = very_large
            mat[i, j] = v
            mat[j, i] = v

    return mat


def count_missing_route_pairs(distance_mat: np.ndarray) -> int:
    n = distance_mat.shape[0]
    if n <= 1:
        return 0
    mask = ~np.isfinite(distance_mat)
    np.fill_diagonal(mask, False)
    return int(mask.sum())
