from collections import deque
from typing import Dict, List, Set, Tuple

import geopandas as gpd
import numpy as np


def build_adjacency_from_geometries(gdf: gpd.GeoDataFrame) -> List[Set[int]]:
    n = len(gdf)
    adjacency = [set() for _ in range(n)]
    if n <= 1:
        return adjacency

    sindex = gdf.sindex
    geoms = list(gdf.geometry)

    for i, geom in enumerate(geoms):
        if geom is None or geom.is_empty:
            continue

        candidates = list(sindex.intersection(geom.bounds))
        for j in candidates:
            if j <= i:
                continue
            other = geoms[j]
            if other is None or other.is_empty:
                continue
            if geom.touches(other) or geom.intersects(other):
                adjacency[i].add(j)
                adjacency[j].add(i)

    return adjacency


def calc_group_medoid(member_indices: List[int], route_mat: np.ndarray) -> int:
    if len(member_indices) == 1:
        return int(member_indices[0])

    sub = route_mat[np.ix_(member_indices, member_indices)]
    scores = np.sum(sub, axis=1)
    best_local = int(np.argmin(scores))
    return int(member_indices[best_local])


def is_connected(indices: List[int], adjacency: List[Set[int]]) -> bool:
    if len(indices) <= 1:
        return True

    member_set = set(indices)
    start = indices[0]
    seen = {start}
    queue = deque([start])

    while queue:
        current = queue.popleft()
        for nxt in adjacency[current]:
            if nxt in member_set and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)

    return len(seen) == len(member_set)


def boundary_candidates(groups: List[List[int]], adjacency: List[Set[int]]) -> List[Tuple[int, int, Set[int]]]:
    group_of = {}
    for g_no, members in enumerate(groups):
        for idx in members:
            group_of[idx] = g_no

    candidates = []
    for g_no, members in enumerate(groups):
        for idx in members:
            neighbor_groups = {group_of[n] for n in adjacency[idx] if group_of.get(n) != g_no}
            if neighbor_groups:
                candidates.append((g_no, idx, neighbor_groups))
    return candidates


def score_group(
    members: List[int],
    pop65_arr: np.ndarray,
    route_mat: np.ndarray,
    target_pop65: float,
    route_scale: float,
):
    if not members:
        return float("inf"), -1, 0.0

    medoid = calc_group_medoid(members, route_mat)
    pop_sum = float(pop65_arr[members].sum())
    cohesion = float(np.mean([route_mat[idx, medoid] for idx in members])) / max(route_scale, 1e-9)
    balance = abs(pop_sum - target_pop65) / target_pop65 if target_pop65 > 0 else 0.0
    score = cohesion + 10.0 * balance
    return score, medoid, pop_sum


def refine_groups_with_route(
    groups: List[List[int]],
    gdf: gpd.GeoDataFrame,
    route_mat: np.ndarray,
    target_pop65: float,
    max_iter: int = 120,
):
    if not groups:
        return groups, {"moves": 0, "iterations": 0}

    groups = [sorted(set(members)) for members in groups]
    pop65_arr = gdf["pop65"].to_numpy(dtype=float)
    adjacency = build_adjacency_from_geometries(gdf)

    finite_vals = route_mat[np.isfinite(route_mat) & (route_mat > 0)]
    route_scale = float(np.median(finite_vals)) if finite_vals.size else 1.0

    moves = 0
    iterations = 0

    for iteration in range(max_iter):
        iterations = iteration + 1
        current_stats = {
            g_no: score_group(members, pop65_arr, route_mat, target_pop65, route_scale)
            for g_no, members in enumerate(groups)
        }

        best_delta = 0.0
        best_move = None

        for src, idx, dst_candidates in boundary_candidates(groups, adjacency):
            if len(groups[src]) <= 1:
                continue

            remaining_src = [m for m in groups[src] if m != idx]
            if not is_connected(remaining_src, adjacency):
                continue

            old_src_score = current_stats[src][0]

            for dst in dst_candidates:
                new_dst_members = groups[dst] + [idx]
                if not any(nei in groups[dst] for nei in adjacency[idx]):
                    continue

                old_dst_score = current_stats[dst][0]
                new_src_score = score_group(remaining_src, pop65_arr, route_mat, target_pop65, route_scale)[0]
                new_dst_score = score_group(new_dst_members, pop65_arr, route_mat, target_pop65, route_scale)[0]

                delta = (old_src_score + old_dst_score) - (new_src_score + new_dst_score)
                if delta > best_delta + 1e-9:
                    best_delta = delta
                    best_move = (src, dst, idx)

        if best_move is None:
            break

        src, dst, idx = best_move
        groups[src].remove(idx)
        groups[dst].append(idx)
        groups[src] = sorted(groups[src])
        groups[dst] = sorted(groups[dst])
        moves += 1

    return groups, {"moves": moves, "iterations": iterations}
