import streamlit as st
import pandas as pd
import glob
import os
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="마케팅 대시보드", layout="wide")

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNEL_DIR = os.path.join(DATA_DIR, "marketing_data", "channel")
AF_DIR = os.path.join(DATA_DIR, "marketing_data", "appsflyer")


AF_COLS = {"일": "date", "미디어소스": "media_source", "캠페인": "campaign",
           "그룹": "adgroup", "소재": "creative", "클릭": "af_click",
           "회원가입": "af_signup", "구매": "af_purchase", "구매매출": "af_revenue"}
CH_COLS = {"일": "date", "채널": "channel", "채널분류": "channel_type",
           "캠페인": "campaign", "캠페인목적": "campaign_goal",
           "그룹": "adgroup", "소재": "creative", "노출": "impression",
           "클릭": "ch_click", "비용": "cost", "회원가입": "ch_signup",
           "구매": "ch_purchase", "구매매출": "ch_revenue"}


def parse_and_merge(af_frames, ch_frames):
    af = pd.concat(af_frames, ignore_index=True).rename(columns=AF_COLS)
    ch = pd.concat(ch_frames, ignore_index=True).rename(columns=CH_COLS)
    merged = ch.merge(
        af[["date", "campaign", "adgroup", "creative", "af_signup", "af_purchase", "af_revenue"]],
        on=["date", "campaign", "adgroup", "creative"], how="left"
    )
    merged["date"] = pd.to_datetime(merged["date"])
    return af, ch, merged


GITHUB_RAW = "https://raw.githubusercontent.com/sjbyun-pixel/marketing-dashboard/master/marketing_data"


@st.cache_data(ttl=300)
def load_data(data_dir):
    # 로컬 폴더 우선
    af_local = glob.glob(os.path.join(data_dir, "marketing_data", "appsflyer", "*.csv"))
    ch_local = glob.glob(os.path.join(data_dir, "marketing_data", "channel", "*.csv"))
    if af_local and ch_local:
        return parse_and_merge(
            [pd.read_csv(f) for f in af_local],
            [pd.read_csv(f) for f in ch_local]
        )

    # GitHub에서 파일 목록 조회 후 로드
    import requests
    def list_github_files(folder):
        api = f"https://api.github.com/repos/sjbyun-pixel/marketing-dashboard/contents/marketing_data/{folder}"
        r = requests.get(api, timeout=10)
        if r.status_code != 200:
            return []
        return [f["download_url"] for f in r.json() if f["name"].endswith(".csv")]

    af_urls = list_github_files("appsflyer")
    ch_urls = list_github_files("channel")

    if not af_urls or not ch_urls:
        return None, None, None

    return parse_and_merge(
        [pd.read_csv(u) for u in af_urls],
        [pd.read_csv(u) for u in ch_urls]
    )


def calc_metrics(d, purchase_col, revenue_col):
    d = d.copy()
    d["_purchase"] = d[purchase_col].fillna(0)
    d["_revenue"] = d[revenue_col].fillna(0)
    d["CTR"] = d["ch_click"] / d["impression"].replace(0, pd.NA) * 100
    d["CVR"] = d["_purchase"] / d["ch_click"].replace(0, pd.NA) * 100
    d["CPA"] = d["cost"] / d["_purchase"].replace(0, pd.NA)
    d["ROAS"] = d["_revenue"] / d["cost"].replace(0, pd.NA) * 100
    return d


def agg_channel(d):
    agg = d.groupby("channel").agg(
        cost=("cost", "sum"),
        revenue=("_revenue", "sum"),
        impression=("impression", "sum"),
        click=("ch_click", "sum"),
        purchase=("_purchase", "sum"),
    ).reset_index()
    agg["CTR"] = agg["click"] / agg["impression"] * 100
    agg["CVR"] = agg["purchase"] / agg["click"] * 100
    agg["CPA"] = agg["cost"] / agg["purchase"]
    agg["ROAS"] = agg["revenue"] / agg["cost"] * 100
    return agg


# ── 데이터 로드
# ── 로컬 폴더 자동 로드 시도
af, ch, df = load_data(DATA_DIR)

if df is None:
    st.title("마케팅 성과 대시보드")
    st.error("데이터가 없습니다. update_data.bat 을 실행해서 데이터를 업로드해주세요.")
    st.stop()

# ── 사이드바
st.sidebar.header("필터")
date_min, date_max = df["date"].min(), df["date"].max()
date_range = st.sidebar.date_input(
    "날짜 범위",
    value=(date_min.date(), date_max.date()),
    min_value=date_min.date(), max_value=date_max.date()
)
channels = ["전체"] + sorted(df["channel"].unique().tolist())
selected_channel = st.sidebar.selectbox("채널", channels)
campaigns = ["전체"] + sorted(df["campaign"].unique().tolist())
selected_campaign = st.sidebar.selectbox("캠페인", campaigns)

st.sidebar.divider()
conv_source = st.sidebar.radio(
    "전환 데이터 소스",
    ["채널 전환", "앱스플라이어 전환"],
    help="구매·매출 기준: 채널 리포트 vs 앱스플라이어(MMP)"
)

st.sidebar.divider()
alert_roas_pct = st.sidebar.number_input("ROAS 이상 임계값 (%)", value=20, min_value=5, max_value=100, step=5,
                                          help="전일 대비 변화율이 이 값 이상이면 경고")
alert_cpa_pct = st.sidebar.number_input("CPA 이상 임계값 (%)", value=20, min_value=5, max_value=100, step=5)
alert_cost_pct = st.sidebar.number_input("비용 이상 임계값 (%)", value=30, min_value=5, max_value=100, step=5)

if st.sidebar.button("데이터 새로고침"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(f"channel {len(glob.glob(os.path.join(CHANNEL_DIR,'*.csv')))}개 | appsflyer {len(glob.glob(os.path.join(AF_DIR,'*.csv')))}개")

# ── 필터 적용
mask = (df["date"].dt.date >= date_range[0]) & (df["date"].dt.date <= date_range[1])
if selected_channel != "전체":
    mask &= df["channel"] == selected_channel
if selected_campaign != "전체":
    mask &= df["campaign"] == selected_campaign
fdf = df[mask].copy()

purchase_col = "ch_purchase" if conv_source == "채널 전환" else "af_purchase"
revenue_col  = "ch_revenue"  if conv_source == "채널 전환" else "af_revenue"
source_label = "채널" if conv_source == "채널 전환" else "앱스플라이어"

fdf = calc_metrics(fdf, purchase_col, revenue_col)

# ── 페이지 탭
st.title("마케팅 성과 대시보드")
page = st.tabs(["📋 Daily Brief", "📊 채널 분석", "🎨 소재 분석", "📈 트렌드"])


# ════════════════════════════════════════
# 📋 Daily Brief
# ════════════════════════════════════════
with page[0]:
    st.caption(f"전환 기준: **{source_label}** | 기간: {date_range[0]} ~ {date_range[1]}")

    # 전일 데이터 분리
    all_dates = sorted(fdf["date"].dt.date.unique())
    has_yesterday = len(all_dates) >= 2
    today_d   = all_dates[-1]
    yest_d    = all_dates[-2] if has_yesterday else all_dates[-1]
    prev_d    = all_dates[-3] if len(all_dates) >= 3 else None

    yest_df = fdf[fdf["date"].dt.date == today_d]
    prev_df  = fdf[fdf["date"].dt.date == yest_d] if has_yesterday else None

    # ① 이상 감지 배너
    st.subheader("이상 감지")

    if not has_yesterday:
        st.info("날짜가 1일치만 있어서 전일 비교 불가.")
    else:
        yest_ch = agg_channel(yest_df)
        prev_ch = agg_channel(prev_df)
        alerts = []
        for _, row in yest_ch.iterrows():
            ch_name = row["channel"]
            prev_row = prev_ch[prev_ch["channel"] == ch_name]
            if prev_row.empty:
                continue
            p = prev_row.iloc[0]
            def pct_chg(a, b):
                return (a - b) / b * 100 if b and b != 0 else 0
            roas_chg = pct_chg(row["ROAS"], p["ROAS"])
            cpa_chg  = pct_chg(row["CPA"],  p["CPA"])
            cost_chg = pct_chg(row["cost"], p["cost"])
            if abs(roas_chg) >= alert_roas_pct:
                icon = "🔴" if roas_chg < 0 else "🟢"
                alerts.append(f"{icon} **{ch_name}** ROAS {roas_chg:+.1f}%  ({p['ROAS']:.0f}% → {row['ROAS']:.0f}%)")
            if abs(cpa_chg) >= alert_cpa_pct:
                icon = "🔴" if cpa_chg > 0 else "🟢"
                alerts.append(f"{icon} **{ch_name}** CPA {cpa_chg:+.1f}%  (₩{p['CPA']:,.0f} → ₩{row['CPA']:,.0f})")
            if abs(cost_chg) >= alert_cost_pct:
                icon = "🟡"
                alerts.append(f"{icon} **{ch_name}** 비용 {cost_chg:+.1f}%  (₩{p['cost']:,.0f} → ₩{row['cost']:,.0f})")

        if alerts:
            for a in alerts:
                st.warning(a)
        else:
            st.success(f"✅ {today_d} 성과 이상 없음 (전일 대비 ROAS/CPA/비용 모두 정상 범위)")

    st.divider()

    # ② 어제 채널별 요약 테이블
    st.subheader(f"채널별 성과 요약 — {today_d}")
    summary = agg_channel(yest_df)

    if has_yesterday:
        prev_summary = agg_channel(prev_df)
        for col, fmt in [("ROAS", "{:+.1f}%"), ("CPA", "{:+.1f}%"), ("cost", "{:+.1f}%")]:
            deltas = []
            for _, row in summary.iterrows():
                prev_row = prev_summary[prev_summary["channel"] == row["channel"]]
                if not prev_row.empty and prev_row.iloc[0][col] != 0:
                    chg = (row[col] - prev_row.iloc[0][col]) / prev_row.iloc[0][col] * 100
                    deltas.append(f"{chg:+.1f}%")
                else:
                    deltas.append("-")
            summary[f"{col}_chg"] = deltas

    display_cols = ["channel", "cost", "impression", "click", "purchase", "revenue", "CTR", "CVR", "CPA", "ROAS"]
    if has_yesterday:
        display_cols += ["cost_chg", "ROAS_chg", "CPA_chg"]

    fmt = {
        "cost": "₩{:,.0f}", "impression": "{:,.0f}", "click": "{:,.0f}",
        "purchase": "{:,.0f}", "revenue": "₩{:,.0f}",
        "CTR": "{:.2f}%", "CVR": "{:.2f}%", "CPA": "₩{:,.0f}", "ROAS": "{:.0f}%",
    }
    st.dataframe(summary[display_cols].style.format(fmt), use_container_width=True, hide_index=True)

    st.divider()

    # ③ 소재 Top3 / Bottom3
    st.subheader(f"소재 ROAS Top 3 / Bottom 3 — {today_d}")
    brief_ch_filter = st.selectbox("채널 선택", ["전체"] + sorted(yest_df["channel"].unique().tolist()), key="brief_ch")
    brief_df = yest_df if brief_ch_filter == "전체" else yest_df[yest_df["channel"] == brief_ch_filter]

    cr = brief_df.groupby(["channel", "campaign", "adgroup", "creative"]).agg(
        cost=("cost", "sum"), revenue=("_revenue", "sum"),
        click=("ch_click", "sum"), purchase=("_purchase", "sum"),
    ).reset_index()
    cr = cr[cr["purchase"] > 0].copy()
    cr["ROAS"] = (cr["revenue"] / cr["cost"] * 100).round(0)
    cr["CPA"]  = (cr["cost"] / cr["purchase"]).round(0)
    cr["CVR"]  = (cr["purchase"] / cr["click"] * 100).round(2)
    cr_sorted  = cr.sort_values("ROAS", ascending=False)

    top3    = cr_sorted.head(3).reset_index(drop=True)
    bottom3 = cr_sorted.tail(3).reset_index(drop=True)

    cr_fmt = {"cost": "₩{:,.0f}", "revenue": "₩{:,.0f}", "click": "{:,.0f}",
              "purchase": "{:,.0f}", "ROAS": "{:.0f}%", "CPA": "₩{:,.0f}", "CVR": "{:.2f}%"}
    cr_cols = ["channel", "campaign", "adgroup", "creative", "cost", "purchase", "revenue", "ROAS", "CPA"]

    col_t, col_b = st.columns(2)
    with col_t:
        st.markdown("🏆 **Top 3**")
        st.dataframe(top3[cr_cols].style.format(cr_fmt), use_container_width=True, hide_index=True)
    with col_b:
        st.markdown("⚠️ **Bottom 3**")
        st.dataframe(bottom3[cr_cols].style.format(cr_fmt), use_container_width=True, hide_index=True)


# ════════════════════════════════════════
# 📊 채널 분석
# ════════════════════════════════════════
with page[1]:
    st.caption(f"전환 기준: **{source_label}**")
    ch_agg = agg_channel(fdf)

    ctab1, ctab2, ctab3, ctab4 = st.tabs(["비용 vs 매출", "전환 지표", "효율 지표", "타겟 분석"])

    with ctab1:
        fig = go.Figure()
        fig.add_bar(name="비용", x=ch_agg["channel"], y=ch_agg["cost"], marker_color="#636EFA")
        fig.add_bar(name="매출", x=ch_agg["channel"], y=ch_agg["revenue"], marker_color="#EF553B")
        fig.update_layout(barmode="group", height=350)
        st.plotly_chart(fig, use_container_width=True)

    with ctab2:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(ch_agg, x="channel", y="CTR", title="채널별 CTR (%)", color="channel")
            fig.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.bar(ch_agg, x="channel", y="CVR", title="채널별 CVR (%)", color="channel")
            fig.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    with ctab3:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(ch_agg, x="channel", y="CPA", title="채널별 CPA (₩)", color="channel")
            fig.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.bar(ch_agg, x="channel", y="ROAS", title="채널별 ROAS (%)", color="channel")
            fig.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    with ctab4:
        st.markdown("##### 타겟 그룹별 성과 버블 차트")
        tgt_agg = fdf.groupby(["channel", "adgroup"]).agg(
            cost=("cost", "sum"), revenue=("_revenue", "sum"),
            click=("ch_click", "sum"), purchase=("_purchase", "sum"),
            impression=("impression", "sum"),
        ).reset_index()
        tgt_agg = tgt_agg[tgt_agg["purchase"] > 0].copy()
        tgt_agg["CPA"]   = tgt_agg["cost"] / tgt_agg["purchase"]
        tgt_agg["ROAS"]  = tgt_agg["revenue"] / tgt_agg["cost"] * 100
        tgt_agg["CTR"]   = tgt_agg["click"] / tgt_agg["impression"] * 100
        tgt_agg["CVR"]   = tgt_agg["purchase"] / tgt_agg["click"] * 100
        tgt_agg["label"] = tgt_agg["channel"] + " / " + tgt_agg["adgroup"]

        b1, b2 = st.columns([3, 1])
        with b2:
            x_axis    = st.selectbox("X축", ["CPA", "CTR", "cost"], key="bubble_x")
            y_axis    = st.selectbox("Y축", ["ROAS", "CVR", "purchase"], key="bubble_y")
            size_axis = st.selectbox("버블 크기", ["cost", "purchase", "impression"], key="bubble_size")
        with b1:
            fig = px.scatter(
                tgt_agg, x=x_axis, y=y_axis, size=size_axis, color="channel",
                text="label",
                hover_data={"channel": True, "adgroup": True, "cost": ":,.0f",
                            "purchase": True, "CPA": ":,.0f", "ROAS": ":.0f"},
                size_max=60, height=450,
            )
            fig.update_traces(textposition="top center", textfont_size=11)
            fig.update_layout(xaxis_title=x_axis, yaxis_title=y_axis, legend_title="채널")
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            tgt_agg[["channel", "adgroup", "impression", "click", "CTR", "cost", "purchase", "revenue", "CPA", "ROAS", "CVR"]]
            .sort_values("cost", ascending=False).reset_index(drop=True)
            .style.format({"cost": "₩{:,.0f}", "revenue": "₩{:,.0f}", "impression": "{:,.0f}",
                           "click": "{:,.0f}", "purchase": "{:,.0f}",
                           "CTR": "{:.2f}%", "CVR": "{:.2f}%", "CPA": "₩{:,.0f}", "ROAS": "{:.0f}%"}),
            use_container_width=True, height=320,
        )


# ════════════════════════════════════════
# 🎨 소재 분석
# ════════════════════════════════════════
with page[2]:
    st.caption(f"전환 기준: **{source_label}**")
    stab1, stab2 = st.tabs(["소재 랭킹", "A/B 비교"])

    with stab1:
        r1, r2, r3, r4 = st.columns([2, 2, 2, 1])
        with r1:
            rank_metric = st.selectbox("정렬 기준", ["cost", "ROAS", "CPA", "CVR", "CTR", "purchase", "revenue"])
        with r2:
            camp_opts = ["전체"] + sorted(fdf["campaign"].unique().tolist())
            rank_camp = st.selectbox("캠페인", camp_opts, key="rank_camp")
        with r3:
            if rank_camp != "전체":
                ag_opts = ["전체"] + sorted(fdf[fdf["campaign"] == rank_camp]["adgroup"].unique().tolist())
            else:
                ag_opts = ["전체"] + sorted(fdf["adgroup"].unique().tolist())
            rank_ag = st.selectbox("그룹", ag_opts, key="rank_ag")
        with r4:
            top_n = st.slider("상위 N개", 5, 50, 10)

        rank_df = fdf.copy()
        if rank_camp != "전체":
            rank_df = rank_df[rank_df["campaign"] == rank_camp]
        if rank_ag != "전체":
            rank_df = rank_df[rank_df["adgroup"] == rank_ag]

        cr_agg = rank_df.groupby(["channel", "campaign", "adgroup", "creative"]).agg(
            cost=("cost", "sum"), impression=("impression", "sum"),
            click=("ch_click", "sum"), purchase=("_purchase", "sum"), revenue=("_revenue", "sum"),
        ).reset_index()
        cr_agg["CTR"]  = (cr_agg["click"] / cr_agg["impression"] * 100).round(2)
        cr_agg["CVR"]  = (cr_agg["purchase"] / cr_agg["click"] * 100).round(2)
        cr_agg["CPC"]  = (cr_agg["cost"] / cr_agg["click"]).round(0)
        cr_agg["CPA"]  = (cr_agg["cost"] / cr_agg["purchase"]).round(0)
        cr_agg["ROAS"] = (cr_agg["revenue"] / cr_agg["cost"] * 100).round(0)

        asc = rank_metric == "CPA"
        ranked = cr_agg.sort_values(rank_metric, ascending=asc).head(top_n).reset_index(drop=True)
        ranked.index += 1

        st.dataframe(
            ranked[["channel", "campaign", "adgroup", "creative",
                    "impression", "click", "CTR", "CPC", "cost", "CVR", "CPA", "ROAS"]].style
            .format({"cost": "₩{:,.0f}", "impression": "{:,.0f}", "click": "{:,.0f}",
                     "CTR": "{:.2f}%", "CPC": "₩{:,.0f}", "CVR": "{:.2f}%",
                     "CPA": "₩{:,.0f}", "ROAS": "{:.0f}%"}),
            use_container_width=True, height=420,
        )

    with stab2:
        st.markdown("##### A소재 vs B소재 비교")
        st.caption("소재명에서 `_A_` / `_B_` 패턴으로 자동 분류")

        ab_df = fdf.copy()
        ab_df["ab_group"] = ab_df["creative"].apply(
            lambda x: "A" if "_A_" in str(x) else ("B" if "_B_" in str(x) else "기타")
        )
        ab_df = ab_df[ab_df["ab_group"].isin(["A", "B"])]

        if ab_df.empty:
            st.info("A/B 소재 데이터 없음. 소재명에 `_A_` 또는 `_B_` 패턴 필요.")
        else:
            ab_ch_filter = st.selectbox("채널", ["전체"] + sorted(ab_df["channel"].unique().tolist()), key="ab_ch")
            if ab_ch_filter != "전체":
                ab_df = ab_df[ab_df["channel"] == ab_ch_filter]

            ab_agg = ab_df.groupby("ab_group").agg(
                cost=("cost", "sum"), impression=("impression", "sum"),
                click=("ch_click", "sum"), purchase=("_purchase", "sum"), revenue=("_revenue", "sum"),
            ).reset_index()
            ab_agg["CTR"]  = (ab_agg["click"] / ab_agg["impression"] * 100).round(2)
            ab_agg["CVR"]  = (ab_agg["purchase"] / ab_agg["click"] * 100).round(2)
            ab_agg["CPA"]  = (ab_agg["cost"] / ab_agg["purchase"]).round(0)
            ab_agg["ROAS"] = (ab_agg["revenue"] / ab_agg["cost"] * 100).round(0)

            # KPI 비교 카드
            metrics = ["cost", "CTR", "CVR", "CPA", "ROAS"]
            labels  = {"cost": "비용", "CTR": "CTR", "CVR": "CVR", "CPA": "CPA", "ROAS": "ROAS"}
            fmts    = {"cost": "₩{:,.0f}", "CTR": "{:.2f}%", "CVR": "{:.2f}%",
                       "CPA": "₩{:,.0f}", "ROAS": "{:.0f}%"}

            cols = st.columns(len(metrics))
            a_row = ab_agg[ab_agg["ab_group"] == "A"].iloc[0] if not ab_agg[ab_agg["ab_group"] == "A"].empty else None
            b_row = ab_agg[ab_agg["ab_group"] == "B"].iloc[0] if not ab_agg[ab_agg["ab_group"] == "B"].empty else None

            for i, m in enumerate(metrics):
                a_val = a_row[m] if a_row is not None else 0
                b_val = b_row[m] if b_row is not None else 0
                delta = b_val - a_val
                fmt_str = fmts[m]
                cols[i].metric(
                    labels[m],
                    f"A: {fmt_str.format(a_val)}",
                    delta=f"B {'+' if delta >= 0 else ''}{fmt_str.format(delta)}",
                    delta_color="normal" if m not in ["CPA", "cost"] else "inverse"
                )

            st.divider()

            # A/B 소재별 상세 테이블
            ab_detail = ab_df.groupby(["ab_group", "channel", "campaign", "adgroup", "creative"]).agg(
                cost=("cost", "sum"), purchase=("_purchase", "sum"), revenue=("_revenue", "sum"),
                click=("ch_click", "sum"),
            ).reset_index()
            ab_detail["ROAS"] = (ab_detail["revenue"] / ab_detail["cost"] * 100).round(0)
            ab_detail["CPA"]  = (ab_detail["cost"] / ab_detail["purchase"]).round(0)
            ab_detail["CVR"]  = (ab_detail["purchase"] / ab_detail["click"] * 100).round(2)

            for grp in ["A", "B"]:
                d = ab_detail[ab_detail["ab_group"] == grp].sort_values("ROAS", ascending=False).reset_index(drop=True)
                if not d.empty:
                    st.markdown(f"**{grp}소재 목록**")
                    st.dataframe(
                        d[["channel", "campaign", "adgroup", "creative", "cost", "purchase", "revenue", "CVR", "CPA", "ROAS"]].style
                        .format({"cost": "₩{:,.0f}", "revenue": "₩{:,.0f}", "purchase": "{:,.0f}",
                                 "CVR": "{:.2f}%", "CPA": "₩{:,.0f}", "ROAS": "{:.0f}%"}),
                        use_container_width=True, hide_index=True,
                    )


# ════════════════════════════════════════
# 📈 트렌드
# ════════════════════════════════════════
with page[3]:
    st.caption(f"전환 기준: **{source_label}**")
    if df["date"].nunique() < 2:
        st.info("날짜가 2일치 이상 있어야 트렌드를 확인할 수 있습니다.")
    else:
        trend_metric = st.selectbox("지표 선택", ["cost", "revenue", "purchase", "ROAS", "CPA", "CTR", "CVR"])
        group_by = st.radio("그룹 기준", ["채널", "캠페인"], horizontal=True)

        group_col = "channel" if group_by == "채널" else "campaign"
        daily = fdf.groupby(["date", group_col]).agg(
            cost=("cost", "sum"), revenue=("_revenue", "sum"),
            purchase=("_purchase", "sum"), click=("ch_click", "sum"),
            impression=("impression", "sum"),
        ).reset_index()
        daily["ROAS"] = daily["revenue"] / daily["cost"] * 100
        daily["CPA"]  = daily["cost"] / daily["purchase"]
        daily["CTR"]  = daily["click"] / daily["impression"] * 100
        daily["CVR"]  = daily["purchase"] / daily["click"] * 100

        fig = px.line(daily, x="date", y=trend_metric, color=group_col, markers=True, height=400)
        fig.update_layout(xaxis_title="날짜", yaxis_title=trend_metric, legend_title=group_by)
        st.plotly_chart(fig, use_container_width=True)
