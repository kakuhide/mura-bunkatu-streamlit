import geopandas as gpd
import pandas as pd
import streamlit as st
from sqlalchemy import text

from config import MAP_CRS, TABLE_NAME, WORK_CRS
from db import get_engine


@st.cache_resource
def get_db_engine():
    return get_engine()


@st.cache_data
def load_city_list() -> pd.DataFrame:
    sql = f'''
        SELECT
            LEFT("地域コード", 5) AS city_code,
            "市区町村名" AS city_name,
            COUNT(*) AS row_count,
            COALESCE(SUM("人口総数"), 0) AS total_population,
            COALESCE(SUM("６５歳以上人口"), 0) AS total_pop65
        FROM {TABLE_NAME}
        WHERE wkb_geometry IS NOT NULL
        GROUP BY LEFT("地域コード", 5), "市区町村名"
        ORDER BY city_code
    '''

    with get_db_engine().connect() as conn:
        conn.execute(text("SET client_encoding TO 'UTF8'"))
        df = pd.read_sql(text(sql), conn)

    df["city_code"] = df["city_code"].astype(str)
    df["row_count"] = df["row_count"].fillna(0).astype(int)
    df["total_population"] = df["total_population"].fillna(0).astype(int)
    df["total_pop65"] = df["total_pop65"].fillna(0).astype(int)
    return df


def _finish_city_blocks_gdf(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf

    gdf = gdf.reset_index(drop=True)
    gdf["population"] = gdf["population"].fillna(0).astype(int)
    gdf["pop65"] = gdf["pop65"].fillna(0).astype(int)

    rep_points = gdf.geometry.representative_point()
    gdf["lon"] = rep_points.x
    gdf["lat"] = rep_points.y

    gdf_work = gdf.to_crs(WORK_CRS)
    rep_points_work = gdf_work.geometry.representative_point()
    gdf["x"] = rep_points_work.x
    gdf["y"] = rep_points_work.y
    return gdf


@st.cache_data
def load_city_blocks(city_name: str) -> gpd.GeoDataFrame:
    """既存互換用。1市区町村名で町丁目を取得する。"""
    sql = f'''
        SELECT
            id,
            "地域コード" AS area_code,
            "都道府県名" AS pref_name,
            "市区町村名" AS city_name,
            "地域名" AS area_name,
            COALESCE("人口総数", 0) AS population,
            COALESCE("６５歳以上人口", 0) AS pop65,
            ST_Transform(wkb_geometry, 4326) AS geom
        FROM {TABLE_NAME}
        WHERE "市区町村名" = %(city_name)s
          AND wkb_geometry IS NOT NULL
        ORDER BY id
    '''

    with get_db_engine().connect() as conn:
        conn.execute(text("SET client_encoding TO 'UTF8'"))
        gdf = gpd.read_postgis(
            sql,
            conn,
            params={"city_name": city_name},
            geom_col="geom",
            crs=MAP_CRS,
        )

    return _finish_city_blocks_gdf(gdf)


@st.cache_data
def load_city_blocks_by_city_codes(city_codes: tuple) -> gpd.GeoDataFrame:
    """複数市区町村コードで町丁目をまとめて取得する。"""
    city_codes = tuple(str(code) for code in city_codes if str(code).strip())
    if not city_codes:
        return gpd.GeoDataFrame(geometry=[], crs=MAP_CRS)

    sql = f'''
        SELECT
            id,
            "地域コード" AS area_code,
            "都道府県名" AS pref_name,
            "市区町村名" AS city_name,
            "地域名" AS area_name,
            COALESCE("人口総数", 0) AS population,
            COALESCE("６５歳以上人口", 0) AS pop65,
            ST_Transform(wkb_geometry, 4326) AS geom
        FROM {TABLE_NAME}
        WHERE LEFT("地域コード", 5) = ANY(%(city_codes)s)
          AND wkb_geometry IS NOT NULL
        ORDER BY LEFT("地域コード", 5), id
    '''

    with get_db_engine().connect() as conn:
        conn.execute(text("SET client_encoding TO 'UTF8'"))
        gdf = gpd.read_postgis(
            sql,
            conn,
            params={"city_codes": list(city_codes)},
            geom_col="geom",
            crs=MAP_CRS,
        )

    return _finish_city_blocks_gdf(gdf)
