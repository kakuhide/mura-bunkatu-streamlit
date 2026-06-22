from sqlalchemy.engine import URL
import streamlit as st

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg2",
    username=st.secrets["database"]["username"],
    password=st.secrets["database"]["password"],
    host=st.secrets["database"]["host"],
    port=int(st.secrets["database"]["port"]),
    database=st.secrets["database"]["database"],
)

TABLE_NAME = "public.chouchoumoku_tokyo"

MAP_CRS = "EPSG:4326"
WORK_CRS = "EPSG:3857"

MAX_SPLIT = 10
DEFAULT_TARGET_POP65 = 15000
DEFAULT_SPLIT_COUNT = 4

GROUP_PALETTE = [
    [44, 62, 80, 180],
    [231, 76, 60, 180],
    [52, 152, 219, 180],
    [46, 204, 113, 180],
    [241, 196, 15, 180],
    [155, 89, 182, 180],
    [26, 188, 156, 180],
    [230, 126, 34, 180],
    [127, 140, 141, 180],
    [192, 57, 43, 180],
    [41, 128, 185, 180],
    [39, 174, 96, 180],
]