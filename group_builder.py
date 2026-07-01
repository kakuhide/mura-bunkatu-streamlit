import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

from config import GROUP_PALETTE, MAP_CRS


def build_groups_gdf(gdf: gpd.GeoDataFrame, groups, show_city_name: bool = False):
    if gdf.empty or not groups:
        return gpd.GeoDataFrame(geometry=[], crs=MAP_CRS), gdf.copy()

    detail_df = gdf.copy()
    detail_df["group_no"] = None
    rows = []

    for i, idx_list in enumerate(groups, start=1):
        sub = gdf.iloc[idx_list].copy()
        detail_df.loc[sub.index, "group_no"] = i

        union_geom = unary_union(list(sub.geometry))
        rep_point = union_geom.representative_point()
        group_pop = int(sub["population"].sum())
        group_pop65 = int(sub["pop65"].sum())

        if show_city_name and "city_name" in sub.columns:
            member_labels = (
                sub["city_name"].astype(str) + " " + sub["area_name"].astype(str)
            ).head(10).tolist()
        else:
            member_labels = sub["area_name"].astype(str).head(10).tolist()

        rows.append(
            {
                "group_no": i,
                "population": group_pop,
                "pop65": group_pop65,
                "block_count": int(len(sub)),
                "area_count": int(sub["area_name"].nunique()),
                "geom": union_geom,
                "centroid": [rep_point.x, rep_point.y],
                "label_text": f"{i}\n{group_pop65:,}人",
                "fill_color": GROUP_PALETTE[(i - 1) % len(GROUP_PALETTE)],
                "member_names": "、".join(member_labels),
            }
        )

    groups_gdf = gpd.GeoDataFrame(rows, geometry="geom", crs=MAP_CRS)
    detail_df["group_no"] = detail_df["group_no"].astype(int)
    return groups_gdf, detail_df


def build_summary_df(groups_gdf: gpd.GeoDataFrame, reference_target_pop65: float) -> pd.DataFrame:
    if groups_gdf.empty:
        return pd.DataFrame()

    df = groups_gdf[["group_no", "population", "pop65", "block_count", "area_count"]].copy()
    target = float(reference_target_pop65) if reference_target_pop65 else 0.0
    df["target_pop65"] = target

    if target > 0:
        df["diff"] = df["pop65"] - target
        df["diff_percent"] = df["diff"] / target * 100.0
    else:
        df["diff"] = 0.0
        df["diff_percent"] = 0.0

    return df.sort_values("group_no")
