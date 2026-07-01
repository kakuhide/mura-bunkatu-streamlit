import hashlib
import math

import plotly.express as px
import pydeck as pdk
import streamlit as st

from config import DEFAULT_SPLIT_COUNT, DEFAULT_TARGET_POP65, MAX_SPLIT
from data_loader import load_city_blocks_by_city_codes, load_city_list
from group_builder import build_groups_gdf, build_summary_df
from map_utils import (
    build_polygon_df,
    build_raw_polygon_df,
    calc_fit_view_state,
    make_polygon_layer,
    make_raw_polygon_layer,
    make_text_layer,
)
from straight_split import split_indices_straight


# --------------------------------------------------
# Utility
# --------------------------------------------------
def calc_auto_split_count(total_city_pop65: int, target_pop65_per_group: int) -> int:
    if total_city_pop65 <= 0 or target_pop65_per_group <= 0:
        return 1
    return max(1, math.ceil(total_city_pop65 / target_pop65_per_group))


def calc_reference_target(
    total_city_pop65: int,
    split_count: int,
    target_input: int,
    basis_mode: str,
) -> float:
    if basis_mode == "人口目標を優先":
        return float(target_input)
    if split_count <= 0:
        return 0.0
    return float(total_city_pop65) / float(split_count)


def clamp_int(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(int(value), max_value))


def make_selection_key(city_codes) -> str:
    joined = "|".join([str(code) for code in city_codes])
    return hashlib.md5(joined.encode("utf-8")).hexdigest()[:12]


def make_area_title(city_names, max_names: int = 4) -> str:
    names = [str(name) for name in city_names]
    if not names:
        return "未選択"
    if len(names) <= max_names:
        return "、".join(names)
    return "、".join(names[:max_names]) + f" ほか{len(names) - max_names}市区町村"


def safe_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def sidebar_readonly_box(label: str, value_text: str, caption: str = ""):
    st.sidebar.markdown(label)
    st.sidebar.markdown(
        f"""
        <div style="
            background:#f1f3f5;
            color:#9ca3af;
            border-radius:8px;
            padding:12px 16px;
            font-size:16px;
            border:1px solid #e5e7eb;
            margin-bottom:4px;
        ">
            {value_text}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if caption:
        st.sidebar.caption(caption)


# --------------------------------------------------
# Page settings
# --------------------------------------------------
st.set_page_config(
    layout="wide",
    page_title="町丁目人口バランス分割（Supabase）",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.4rem !important;
        padding-bottom: 0.4rem !important;
        max-width: 100% !important;
    }
    [data-testid="stPydeckChart"] {
        height: calc(100vh - 100px) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------
# 市区町村一覧
# --------------------------------------------------
city_df = load_city_list()
if city_df.empty:
    st.error("市区町村一覧が取得できませんでした。DB接続またはテーブルを確認してください。")
    st.stop()

city_df = city_df.copy()
city_df["city_code"] = city_df["city_code"].astype(str)
city_df["city_label"] = city_df.apply(
    lambda r: f'{r["city_code"]} {r["city_name"]}', axis=1
)

city_options = city_df["city_code"].tolist()
city_label_map = dict(zip(city_df["city_code"], city_df["city_label"]))

central_matches = city_df.index[city_df["city_name"] == "中央区"].tolist()
if central_matches:
    default_city_code = str(city_df.loc[int(central_matches[0]), "city_code"])
else:
    default_city_code = str(city_df.iloc[0]["city_code"])

# --------------------------------------------------
# Header / mode
# --------------------------------------------------
if "multi_city_mode" not in st.session_state:
    st.session_state["multi_city_mode"] = False

if "single_city_code" not in st.session_state:
    st.session_state["single_city_code"] = default_city_code

if st.session_state["single_city_code"] not in city_options:
    st.session_state["single_city_code"] = default_city_code

mode_title = "複数市区町村" if st.session_state["multi_city_mode"] else "単一市区町村"
mode_description = (
    "複数の市区町村を1つの対象エリアとしてまとめて分割します。"
    if st.session_state["multi_city_mode"]
    else "1つの市区町村を対象に、町丁目単位で分割します。"
)

st.sidebar.markdown(
    f"""
    <div style="line-height:1.45; margin-bottom:12px;">
      <div style="font-size:22px; font-weight:700; color:#222;">
        町丁目人口バランス分割
      </div>
      <div style="font-size:15px; font-weight:600; color:#333; margin-top:8px;">
        {mode_title} / Supabase / PostGIS
      </div>
      <div style="font-size:12px; color:#777; margin-top:8px;">
        {mode_description}
      </div>
      <hr style="margin-top:14px; margin-bottom:14px;">
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------
# モード切替
# --------------------------------------------------
st.sidebar.markdown("### 選択モード")

if st.session_state["multi_city_mode"]:
    st.sidebar.info("現在：複数市区町村モード")
    if st.sidebar.button("単一市区町村選択に戻す", use_container_width=True):
        current_multi = st.session_state.get("multi_city_codes", [])
        if current_multi:
            st.session_state["single_city_code"] = str(current_multi[0])
        st.session_state["multi_city_mode"] = False
        safe_rerun()
else:
    st.sidebar.info("現在：単一市区町村モード")
    if st.sidebar.button("複数市区町村対応に切り替え", use_container_width=True):
        current_single = str(st.session_state.get("single_city_code", default_city_code))
        if current_single not in city_options:
            current_single = default_city_code
        st.session_state["multi_city_codes"] = [current_single]
        st.session_state["multi_city_mode"] = True
        safe_rerun()

st.sidebar.markdown("---")

# --------------------------------------------------
# 市区町村選択
# --------------------------------------------------
if st.session_state["multi_city_mode"]:
    current_multi_codes = st.session_state.get("multi_city_codes", [default_city_code])
    current_multi_codes = [str(code) for code in current_multi_codes if str(code) in city_options]
    if not current_multi_codes:
        current_multi_codes = [default_city_code]
    st.session_state["multi_city_codes"] = current_multi_codes

    selected_city_codes = st.sidebar.multiselect(
        "1. 市区町村（複数選択可）",
        options=city_options,
        default=current_multi_codes,
        format_func=lambda code: city_label_map.get(str(code), str(code)),
        key="multi_city_codes",
        help="複数選択した市区町村を1つの対象エリアとして分割します。",
    )
else:
    current_single_code = str(st.session_state.get("single_city_code", default_city_code))
    if current_single_code not in city_options:
        current_single_code = default_city_code

    selected_city_code = st.sidebar.selectbox(
        "1. 市区町村",
        options=city_options,
        index=city_options.index(current_single_code),
        format_func=lambda code: city_label_map.get(str(code), str(code)),
        key="single_city_code",
        help="単一の市区町村を対象に分割します。",
    )
    selected_city_codes = [str(selected_city_code)]

if not selected_city_codes:
    st.warning("市区町村を1つ以上選択してください。")
    st.stop()

selected_city_codes = [str(code) for code in selected_city_codes]
selected_city_df = city_df[city_df["city_code"].isin(selected_city_codes)].copy()
selected_city_df["_order"] = selected_city_df["city_code"].map(
    {code: i for i, code in enumerate(selected_city_codes)}
)
selected_city_df = selected_city_df.sort_values("_order")
selected_city_names = selected_city_df["city_name"].astype(str).tolist()
selected_area_title = make_area_title(selected_city_names)
selection_key = make_selection_key(selected_city_codes)
is_multi_city_mode = st.session_state["multi_city_mode"]

# --------------------------------------------------
# 選択範囲メタ情報
# --------------------------------------------------
row_count = int(selected_city_df["row_count"].sum())
total_city_pop = int(selected_city_df["total_population"].sum())
total_city_pop65 = int(selected_city_df["total_pop65"].sum())
max_split_available = max(1, min(MAX_SPLIT, row_count))

if is_multi_city_mode:
    st.sidebar.metric("選択市区町村数", f"{len(selected_city_codes):,} 件")

st.sidebar.metric("総人口", f"{total_city_pop:,} 人")
st.sidebar.metric("65歳以上人口", f"{total_city_pop65:,} 人")
st.sidebar.metric("町丁目数", f"{row_count:,} 件")

if is_multi_city_mode:
    with st.sidebar.expander("選択中の市区町村", expanded=False):
        st.dataframe(
            selected_city_df[["city_code", "city_name", "row_count", "total_population", "total_pop65"]]
            .rename(
                columns={
                    "city_code": "市区町村コード",
                    "city_name": "市区町村",
                    "row_count": "町丁目数",
                    "total_population": "総人口",
                    "total_pop65": "65歳以上人口",
                }
            ),
            width="stretch",
            hide_index=True,
        )

# --------------------------------------------------
# 採用基準
# --------------------------------------------------
basis_mode = st.sidebar.radio(
    "2. 採用する基準",
    ["人口目標を優先", "分割数を優先"],
    index=0,
)

is_target_mode = basis_mode == "人口目標を優先"
is_split_mode = basis_mode == "分割数を優先"

target_key = f"target_pop65_{selection_key}"
split_key = f"manual_split_{selection_key}"

target_min = 1
target_max = max(1, total_city_pop65) if total_city_pop65 > 0 else 1
target_default = min(DEFAULT_TARGET_POP65, target_max) if total_city_pop65 > 0 else 1

current_target_value = clamp_int(
    st.session_state.get(target_key, target_default),
    target_min,
    target_max,
)

split_min = 1
split_max = max_split_available
split_default = min(DEFAULT_SPLIT_COUNT, max_split_available)

current_split_value = clamp_int(
    st.session_state.get(split_key, split_default),
    split_min,
    split_max,
)

# --------------------------------------------------
# 入力欄
# --------------------------------------------------
if is_target_mode:
    target_pop65_input = int(
        st.sidebar.number_input(
            "3. 1分割あたりの65歳以上人口",
            min_value=target_min,
            max_value=target_max,
            value=current_target_value,
            step=1000,
            key=target_key,
        )
    )
else:
    target_pop65_input = current_target_value
    sidebar_readonly_box(
        "3. 1分割あたりの65歳以上人口",
        f"{target_pop65_input:,}",
        "分割数を優先しているため編集できません。",
    )

auto_split_count = calc_auto_split_count(total_city_pop65, target_pop65_input)

if is_split_mode:
    manual_split_input = int(
        st.sidebar.number_input(
            "4. 分割数",
            min_value=split_min,
            max_value=split_max,
            value=current_split_value,
            step=1,
            key=split_key,
        )
    )
else:
    manual_split_input = current_split_value
    sidebar_readonly_box(
        "4. 分割数",
        f"{auto_split_count:,}",
        "人口目標を優先しているため、分割数は自動計算されます。",
    )

# --------------------------------------------------
# 実行分割数
# --------------------------------------------------
requested_split_count = auto_split_count if is_target_mode else manual_split_input

effective_split_count = max(1, min(requested_split_count, row_count, MAX_SPLIT))

reference_target_pop65 = calc_reference_target(
    total_city_pop65,
    effective_split_count,
    target_pop65_input,
    basis_mode,
)

st.sidebar.metric("人口目標からの自動分割数", f"{auto_split_count:,}")
st.sidebar.metric("実行分割数", f"{effective_split_count:,}")

if requested_split_count > MAX_SPLIT:
    st.sidebar.caption(
        f"指定値からは {requested_split_count} 分割ですが、上限 {MAX_SPLIT} のため "
        f"{effective_split_count} 分割で実行します。"
    )
elif requested_split_count > row_count:
    st.sidebar.caption(
        f"指定値からは {requested_split_count} 分割ですが、町丁目数上限のため "
        f"{effective_split_count} 分割で実行します。"
    )

show_labels = st.sidebar.checkbox("🏷 ラベル表示", value=True)
show_raw_blocks = st.sidebar.checkbox("▫ 元の町丁目境界を薄く表示", value=False)

# --------------------------------------------------
# データ読み込み
# --------------------------------------------------
load_text = "選択した市区町村データを読み込み中です..." if is_multi_city_mode else "市区町村データを読み込み中です..."
with st.spinner(load_text):
    city_blocks = load_city_blocks_by_city_codes(tuple(selected_city_codes))

if city_blocks.empty:
    st.error("選択した市区町村のデータがありません。")
    st.stop()

# --------------------------------------------------
# 直線ロジックで分割
# --------------------------------------------------
with st.spinner("直線ロジックで分割中です..."):
    final_groups = split_indices_straight(city_blocks, effective_split_count)

groups_gdf, detail_df = build_groups_gdf(
    city_blocks,
    final_groups,
    show_city_name=is_multi_city_mode,
)
summary_df = build_summary_df(groups_gdf, reference_target_pop65)

distance_status_text = "直線のみ"

# --------------------------------------------------
# サイドバー集計
# --------------------------------------------------
if not summary_df.empty:
    max_abs_error = float(summary_df["diff_percent"].abs().max())
    avg_abs_error = float(summary_df["diff_percent"].abs().mean())

    st.sidebar.metric("65歳以上人口 最大誤差", f"{max_abs_error:.2f}%")
    st.sidebar.metric("65歳以上人口 平均誤差", f"{avg_abs_error:.2f}%")

    bar_fig = px.bar(
        summary_df,
        x="group_no",
        y="pop65",
        text="pop65",
        labels={"group_no": "グループ", "pop65": "65歳以上人口"},
        title=f"グループ別 65歳以上人口（{distance_status_text}）",
    )
    bar_fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    bar_fig.update_layout(height=260, margin=dict(l=10, r=10, t=40, b=10))
    st.sidebar.plotly_chart(bar_fig, width="stretch")

# --------------------------------------------------
# 地図レイヤー作成
# --------------------------------------------------
poly_df = build_polygon_df(groups_gdf)
city_bounds = city_blocks.total_bounds
view_state = calc_fit_view_state(city_bounds)

layers = []

if show_raw_blocks:
    raw_df = build_raw_polygon_df(city_blocks)
    if not raw_df.empty:
        layers.append(make_raw_polygon_layer(raw_df))

layers.append(make_polygon_layer(poly_df, layer_id="split_groups", pickable=True))

if show_labels:
    layers.append(
        make_text_layer(
            groups_gdf[["centroid", "label_text"]].copy(),
            "group_labels",
        )
    )

deck = pdk.Deck(
    layers=layers,
    initial_view_state=view_state,
    map_style=pdk.map_styles.ROAD,
    tooltip={
        "html": """
            <b>グループ {group_no}</b><br/>
            65歳以上: {pop65} 人<br/>
            総人口: {population} 人<br/>
            町丁目数: {block_count}
        """,
        "style": {
            "backgroundColor": "rgba(30,30,30,0.85)",
            "color": "white",
            "fontSize": "13px",
        },
    },
)

# --------------------------------------------------
# 画面表示
# --------------------------------------------------
left, right = st.columns([3.2, 1.4])

with left:
    st.pydeck_chart(deck, height=850, width="stretch")

with right:
    st.markdown("<div style='padding-top: 14px;'></div>", unsafe_allow_html=True)
    st.markdown(f"### 📊 {selected_area_title}")
    st.write(f"選択モード: **{mode_title}**")
    if is_multi_city_mode:
        st.write(f"選択市区町村数: **{len(selected_city_codes):,} 件**")
    st.write(f"実行方法: **{distance_status_text}**")
    st.write(f"採用基準: **{basis_mode}**")

    if is_multi_city_mode:
        if len(selected_city_names) <= 8:
            st.caption("選択中: " + "、".join(selected_city_names))
        else:
            st.caption(
                "選択中: "
                + "、".join(selected_city_names[:8])
                + f" ほか{len(selected_city_names) - 8}市区町村"
            )

    if is_target_mode:
        st.write(f"入力した人口目標: **{target_pop65_input:,} 人**")
        st.write(f"自動計算された分割数: **{auto_split_count:,}**")
    else:
        st.write(f"入力した分割数: **{manual_split_input:,}**")
        st.write(
            f"1分割あたりの参考65歳以上人口: "
            f"**{reference_target_pop65:,.2f} 人**"
        )

    st.write(f"実行分割数: **{effective_split_count:,}**")
    st.write(f"評価用の目標65歳以上人口: **{reference_target_pop65:,.2f} 人**")

    if is_multi_city_mode:
        st.caption("※ 複数市区町村を1つの対象エリアとしてまとめて分割します。")
    else:
        st.caption("※ 単一市区町村を対象に分割します。")
    st.caption("※ 町丁目ポリゴンは分割せず、町丁目単位でグループ化しています。")
    st.caption("※ 直線ロジックで65歳以上人口がなるべく均等になるように分割しています。")

    display_df = summary_df.copy()

    if not display_df.empty:
        display_df["population"] = display_df["population"].map(lambda x: f"{int(x):,}")
        display_df["pop65"] = display_df["pop65"].map(lambda x: f"{int(x):,}")
        display_df["target_pop65"] = display_df["target_pop65"].map(lambda x: f"{x:,.2f}")
        display_df["diff"] = display_df["diff"].map(lambda x: f"{x:+,.2f}")
        display_df["diff_percent"] = display_df["diff_percent"].map(lambda x: f"{x:+.2f}%")

        st.dataframe(
            display_df.rename(
                columns={
                    "group_no": "グループ",
                    "population": "人口総数",
                    "pop65": "65歳以上人口",
                    "block_count": "町丁目数",
                    "area_count": "地域名数",
                    "target_pop65": "目標65歳以上人口",
                    "diff": "差分",
                    "diff_percent": "差分率",
                }
            ),
            width="stretch",
            hide_index=True,
        )

    st.markdown("#### グループ別の主な地域名")
    for row in groups_gdf.sort_values("group_no").itertuples():
        st.write(f"**{row.group_no}**: {row.member_names}")

st.markdown("---")
st.markdown("#### 補足")
st.write("この版では、道のり距離補正は使用せず、直線ロジックのみで町丁目を分割しています。")
st.write("初期表示は単一市区町村モードです。必要な場合だけ、複数市区町村対応に切り替えます。")
st.write("複数市区町村モードでは、選択した市区町村全体を1つの対象エリアとして扱います。")
st.write("「人口目標を優先」を選ぶと、1分割あたりの65歳以上人口だけ編集できます。")
st.write("「分割数を優先」を選ぶと、分割数だけ編集できます。")
