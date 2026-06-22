import math

import pandas as pd
import pydeck as pdk
from shapely.geometry import MultiPolygon, Polygon


def polygon_exterior_coords(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [list(coord) for coord in geom.exterior.coords]
    return []


def build_polygon_df(gdf) -> pd.DataFrame:
    rows = []
    for row in gdf.itertuples():
        geom = row.geom
        base = {
            "group_no": int(row.group_no),
            "population": int(row.population),
            "pop65": int(row.pop65),
            "block_count": int(row.block_count),
            "label_text": row.label_text,
            "fill_color": row.fill_color,
        }

        if geom is None or geom.is_empty:
            continue

        if isinstance(geom, Polygon):
            rows.append({**base, "polygon": polygon_exterior_coords(geom)})
        elif isinstance(geom, MultiPolygon):
            for poly in geom.geoms:
                rows.append({**base, "polygon": polygon_exterior_coords(poly)})

    return pd.DataFrame(rows)


def build_raw_polygon_df(gdf) -> pd.DataFrame:
    rows = []
    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            continue
        if isinstance(geom, Polygon):
            rows.append({"polygon": polygon_exterior_coords(geom)})
        elif isinstance(geom, MultiPolygon):
            for poly in geom.geoms:
                rows.append({"polygon": polygon_exterior_coords(poly)})
    return pd.DataFrame(rows)


def make_polygon_layer(df: pd.DataFrame, layer_id: str, pickable: bool = True) -> pdk.Layer:
    return pdk.Layer(
        "PolygonLayer",
        df,
        id=layer_id,
        get_polygon="polygon",
        get_fill_color="fill_color",
        get_line_color=[70, 70, 70, 180],
        line_width_min_pixels=2,
        pickable=pickable,
        auto_highlight=True,
        highlight_color=[0, 120, 255, 80],
    )


def make_raw_polygon_layer(df: pd.DataFrame, layer_id: str = "raw_blocks") -> pdk.Layer:
    return pdk.Layer(
        "PolygonLayer",
        df,
        id=layer_id,
        get_polygon="polygon",
        get_fill_color=[0, 0, 0, 0],
        get_line_color=[120, 120, 120, 80],
        line_width_min_pixels=1,
        pickable=False,
    )


def make_text_layer(df: pd.DataFrame, layer_id: str) -> pdk.Layer:
    layer = pdk.Layer(
        "TextLayer",
        df,
        id=layer_id,
        get_position="centroid",
        get_text="label_text",
        get_color=[255, 255, 255, 255],
        get_size=18,
        get_alignment_baseline="'center'",
        get_text_anchor="'middle'",
        pickable=False,
    )
    layer.characterSet = "auto"
    return layer


def calc_fit_view_state(bounds, map_width_px: int = 950, map_height_px: int = 850, padding: float = 1.15):
    minx, miny, maxx, maxy = [float(v) for v in bounds]

    center_x = (minx + maxx) / 2.0
    center_y = (miny + maxy) / 2.0

    lon_span = max((maxx - minx) * padding, 0.0005)
    lat_span = max((maxy - miny) * padding, 0.0005)

    world_dim = 512.0

    def lat_to_mercator_fraction(lat_deg: float) -> float:
        lat_rad = math.radians(lat_deg)
        value = math.log(math.tan(math.pi / 4.0 + lat_rad / 2.0))
        return value / math.pi

    zoom_lon = math.log2((360.0 * float(map_width_px)) / (lon_span * world_dim))

    merc_min = lat_to_mercator_fraction(miny)
    merc_max = lat_to_mercator_fraction(maxy)
    merc_span = max(abs(merc_max - merc_min) * padding, 1e-9)
    zoom_lat = math.log2((2.0 * float(map_height_px)) / (merc_span * world_dim))

    zoom = min(zoom_lon, zoom_lat)
    zoom = max(7.0, min(16.0, zoom))

    return pdk.ViewState(
        latitude=center_y,
        longitude=center_x,
        zoom=zoom,
        pitch=0,
    )
