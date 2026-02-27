import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="SKU Performance Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
    div[data-testid="stMetric"] {
        background: #0e1117; border: 1px solid #262730; border-radius: 8px;
        padding: 12px 16px; box-shadow: 0 1px 3px rgba(0,0,0,.3);
    }
    div[data-testid="stMetric"] label {font-size: 0.82rem !important; color: #9ca3af !important;}
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {font-size: 1.5rem !important;}
    .insight-box {
        background: #1a1d23; border-left: 4px solid #3b82f6; border-radius: 6px;
        padding: 12px 16px; margin: 8px 0; font-size: 0.88rem; line-height: 1.5;
    }
    .risk-box {
        background: #1c1012; border-left: 4px solid #ef4444; border-radius: 6px;
        padding: 12px 16px; margin: 8px 0; font-size: 0.88rem; line-height: 1.5;
    }
    .growth-box {
        background: #0f1c14; border-left: 4px solid #22c55e; border-radius: 6px;
        padding: 12px 16px; margin: 8px 0; font-size: 0.88rem; line-height: 1.5;
    }
    section[data-testid="stSidebar"] {background: #0a0c10;}
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        justify-content: stretch;
        width: 100%;
    }
    .stTabs [data-baseweb="tab"] {
        background: #1a1d23; border-radius: 6px 6px 0 0;
        padding: 10px 0;
        flex: 1 1 0;
        text-align: center;
        white-space: nowrap;
        font-size: 0.92rem;
        letter-spacing: 0.01em;
    }
</style>
""", unsafe_allow_html=True)


# ── Data Loading ────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv("listingdata_final_for_looker.csv")
    df["date"] = pd.to_datetime(df["date"], dayfirst=True)
    return df


raw = load_data()

LATEST_DATE = raw["date"].max()

# Deduplicated item-level view (revenue lives at item_id level, not variant)
item_df = raw.drop_duplicates(subset=["item_id", "date"]).copy()

# ── Sidebar Filters ─────────────────────────────────────────────────────────
st.sidebar.markdown("## Filters")

FILTER_DEFAULTS = {
    "f_start": raw["date"].min().date(),
    "f_end": LATEST_DATE.date(),
    "f_brands": [],
    "f_rating": 4.0,
    "f_count": 200,
    "f_growth": 20,
    "f_skus": [],
}

def _clear_filters():
    for k, v in FILTER_DEFAULTS.items():
        st.session_state[k] = v

if "f_start" not in st.session_state:
    st.session_state["f_start"] = FILTER_DEFAULTS["f_start"]
if "f_end" not in st.session_state:
    st.session_state["f_end"] = FILTER_DEFAULTS["f_end"]

col_sd, col_ed = st.sidebar.columns(2)
with col_sd:
    start_date = st.date_input(
        "Start Date",
        min_value=raw["date"].min().date(),
        max_value=LATEST_DATE.date(),
        format="DD-MM-YYYY",
        key="f_start",
    )
with col_ed:
    end_date = st.date_input(
        "End Date",
        min_value=raw["date"].min().date(),
        max_value=LATEST_DATE.date(),
        format="DD-MM-YYYY",
        key="f_end",
    )
date_start, date_end = pd.Timestamp(start_date), pd.Timestamp(end_date)
if date_start > date_end:
    st.sidebar.error("Start Date must be before End Date.")
    st.stop()

item_df = item_df[(item_df["date"] >= date_start) & (item_df["date"] <= date_end)]
LATEST_DATE = item_df["date"].max()
FOUR_W_AGO = LATEST_DATE - pd.Timedelta(weeks=4)
nearest_4w = item_df["date"].unique()
nearest_4w = pd.Timestamp(min(nearest_4w, key=lambda d: abs(d - FOUR_W_AGO)))

all_brands = sorted(item_df["brand_name"].unique())
sel_brands = st.sidebar.multiselect("Brand (leave empty = all)", all_brands, default=[], key="f_brands")
active_brands = sel_brands if sel_brands else all_brands

rating_thresh = st.sidebar.slider("Min Rating Threshold", 1.0, 5.0, 4.0, 0.1, key="f_rating")
count_thresh = st.sidebar.slider("Min Rating Count Threshold", 0, 5000, 200, 50, key="f_count")
growth_thresh = st.sidebar.slider("Growth % Threshold (High-Scaling)", 0, 100, 20, 5, key="f_growth")

all_skus = sorted(item_df[item_df["brand_name"].isin(active_brands)]["item_id"].unique())
sel_skus = st.sidebar.multiselect("SKU Selector (leave empty = all)", all_skus, default=[], key="f_skus")
active_skus = sel_skus if sel_skus else all_skus

filt = item_df[(item_df["brand_name"].isin(active_brands)) & (item_df["item_id"].isin(active_skus))]

st.sidebar.markdown("---")
st.sidebar.button("Clear Filters", use_container_width=True, on_click=_clear_filters)

# ── Helper: format currency ─────────────────────────────────────────────────
def fmt_inr(v):
    if abs(v) >= 1e7:
        return f"₹{v / 1e7:.2f} Cr"
    if abs(v) >= 1e5:
        return f"₹{v / 1e5:.2f} L"
    if abs(v) >= 1e3:
        return f"₹{v / 1e3:.1f} K"
    return f"₹{v:,.0f}"


# ── KPI Computation ─────────────────────────────────────────────────────────
latest = filt[filt["date"] == LATEST_DATE]
prev = filt[filt["date"] == nearest_4w]

total_rev_latest = latest["revenue"].sum()
total_rev_4w = prev["revenue"].sum()
growth_pct = ((total_rev_latest - total_rev_4w) / total_rev_4w * 100) if total_rev_4w else 0

risky = latest[(latest["rating"] < rating_thresh) & (latest["rating_count"] > count_thresh)]
rev_at_risk = risky["revenue"].sum()

# Per-SKU growth
sku_latest = latest.groupby("item_id").agg(
    revenue_latest=("revenue", "first"),
    rating=("rating", "first"),
    rating_count=("rating_count", "first"),
    brand_name=("brand_name", "first"),
    title=("title", "first"),
).reset_index()

sku_prev = prev.groupby("item_id").agg(revenue_4w=("revenue", "first")).reset_index()
sku_merged = sku_latest.merge(sku_prev, on="item_id", how="left")
sku_merged["growth_pct"] = sku_merged.apply(
    lambda r: ((r["revenue_latest"] - r["revenue_4w"]) / r["revenue_4w"] * 100)
    if pd.notna(r["revenue_4w"]) and r["revenue_4w"] > 0 else None, axis=1
)

high_scaling = sku_merged[
    (sku_merged["growth_pct"] > growth_thresh) & (sku_merged["rating"] >= rating_thresh)
]
high_scaling_count = len(high_scaling)
high_scaling_rev = high_scaling["revenue_latest"].sum()

avg_rating = latest["rating"].mean() if len(latest) else 0

# ── Title ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="display:flex; justify-content:space-between; align-items:baseline;">'
    '<h1 style="margin:0;">SKU Performance Dashboard</h1>'
    '<span style="color:#9ca3af; font-size:0.95rem; white-space:nowrap;">By Abhiraj Singh</span>'
    '</div>',
    unsafe_allow_html=True,
)
st.caption(
    f"Total Records: **{len(filt):,}**  ·  "
    f"Total SKUs: **{filt['item_id'].nunique()}**  ·  "
    f"Total Brands: **{filt['brand_name'].nunique()}**  ·  "
    f"Latest date: **{LATEST_DATE.strftime('%d %b %Y')}**  ·  "
    f"4W comparison: **{nearest_4w.strftime('%d %b %Y')}**  ·  "
    f"Active on latest: **{latest['item_id'].nunique()} SKUs**"
)

# ── KPI Row ─────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total Revenue (Latest)", fmt_inr(total_rev_latest))
k2.metric("Portfolio 4W Growth", f"{growth_pct:+.1f}%",
          delta=f"{growth_pct:+.1f}%", delta_color="normal")
k3.metric("Revenue At Risk", fmt_inr(rev_at_risk),
          delta=f"{risky['item_id'].nunique()} SKU(s)", delta_color="inverse")
k4.metric("High-Scaling SKUs", f"{high_scaling_count}",
          delta=f"{fmt_inr(high_scaling_rev)} rev", delta_color="normal")
k5.metric("High-Scaling Revenue", fmt_inr(high_scaling_rev))
k6.metric("Avg Portfolio Rating", f"{avg_rating:.2f}" if avg_rating else "N/A")

# ── Strategic Insight Bar ───────────────────────────────────────────────────
st.markdown("---")

if rev_at_risk > 0:
    risk_share = rev_at_risk / total_rev_latest * 100 if total_rev_latest else 0
    st.markdown(
        f'<div class="risk-box"><strong>Revenue at Risk:</strong> '
        f'{fmt_inr(rev_at_risk)} ({risk_share:.1f}% of portfolio) is concentrated in '
        f'{risky["item_id"].nunique()} SKU(s) with rating &lt; {rating_thresh} and '
        f'&gt; {count_thresh} reviews. <strong>Action:</strong> Investigate product quality, '
        f'review sentiment, and consider listing optimization or price adjustment.</div>',
        unsafe_allow_html=True,
    )

if high_scaling_count > 0:
    hs_share = high_scaling_rev / total_rev_latest * 100 if total_rev_latest else 0
    st.markdown(
        f'<div class="growth-box"><strong>Growth Opportunity:</strong> '
        f'{high_scaling_count} SKU(s) growing &gt;{growth_thresh}% with rating &ge; {rating_thresh}, '
        f'contributing {fmt_inr(high_scaling_rev)} ({hs_share:.1f}% of portfolio). '
        f'<strong>Action:</strong> Increase ad spend, secure inventory, and expand variant assortment.</div>',
        unsafe_allow_html=True,
    )

if growth_pct < 0:
    st.markdown(
        f'<div class="risk-box"><strong>Portfolio Declining:</strong> '
        f'Overall revenue fell {growth_pct:.1f}% over 4 weeks. '
        f'<strong>Action:</strong> Audit underperforming SKUs, review competitive pricing, '
        f'and check for stock-out or suppression issues.</div>',
        unsafe_allow_html=True,
    )
elif growth_pct > 0:
    st.markdown(
        f'<div class="insight-box"><strong>Portfolio Health:</strong> '
        f'Revenue grew {growth_pct:.1f}% over 4 weeks from {fmt_inr(total_rev_4w)} to '
        f'{fmt_inr(total_rev_latest)}. Monitor sustainability and reinvest in top performers.</div>',
        unsafe_allow_html=True,
    )

# ── Tabs ────────────────────────────────────────────────────────────────────
tab_overview, tab_brand, tab_risk, tab_growth, tab_trend = st.tabs([
    "Overview", "Brand Analysis", "Risk Monitor", "Growth Drivers", "Trend Explorer"
])

# ─── TAB 1: Overview ────────────────────────────────────────────────────────
with tab_overview:
    st.markdown("### Revenue vs 4-Week Growth % (SKU-level)")
    st.markdown(
        '<div class="insight-box"><strong>Why it matters:</strong> Identifies which SKUs '
        'combine scale with momentum. Top-right quadrant = stars to invest in. '
        'Bottom-left = candidates for review or discontinuation.</div>',
        unsafe_allow_html=True,
    )

    scatter_data = sku_merged.dropna(subset=["growth_pct"]).copy()
    scatter_data["size_val"] = scatter_data["revenue_latest"].clip(lower=1)
    scatter_data["risk_label"] = scatter_data.apply(
        lambda r: "At Risk" if r["rating"] < rating_thresh and r["rating_count"] > count_thresh
        else ("High-Scaling" if r["growth_pct"] > growth_thresh and r["rating"] >= rating_thresh
              else "Stable"), axis=1
    )

    color_map = {"At Risk": "#ef4444", "High-Scaling": "#22c55e", "Stable": "#6b7280"}
    fig_scatter = px.scatter(
        scatter_data, x="growth_pct", y="revenue_latest",
        size="size_val", color="risk_label",
        color_discrete_map=color_map,
        hover_data={"item_id": True, "brand_name": True, "rating": True,
                    "revenue_latest": ":,.0f", "growth_pct": ":.1f", "size_val": False},
        labels={"growth_pct": "4-Week Growth %", "revenue_latest": "Latest Revenue (₹)",
                "risk_label": "Status"},
        size_max=45,
    )
    fig_scatter.add_vline(x=growth_thresh, line_dash="dot", line_color="#22c55e", opacity=0.4,
                          annotation_text=f"+{growth_thresh}% growth")
    fig_scatter.add_vline(x=0, line_dash="dash", line_color="#6b7280", opacity=0.3)
    fig_scatter.update_layout(
        template="plotly_dark", height=480,
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        margin=dict(l=40, r=20, t=30, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

# ─── TAB 2: Brand Analysis ──────────────────────────────────────────────────
with tab_brand:
    st.markdown("### Brand-wise Revenue Contribution (Latest)")
    st.markdown(
        '<div class="insight-box"><strong>Why it matters:</strong> Concentration risk — if '
        'top 2-3 brands drive &gt;60% of revenue, any disruption (stock-out, delisting, '
        'rating drop) can crater the portfolio. <strong>Action:</strong> Diversify if '
        'concentration is high; double down on growing brands.</div>',
        unsafe_allow_html=True,
    )

    brand_rev = latest.groupby("brand_name")["revenue"].sum().reset_index()
    brand_rev = brand_rev.sort_values("revenue", ascending=True)
    brand_rev["pct"] = brand_rev["revenue"] / brand_rev["revenue"].sum() * 100

    brand_rev["label"] = brand_rev.apply(
        lambda r: f"Rev: {fmt_inr(r['revenue'])} | Share: {r['pct']:.1f}%", axis=1
    )
    fig_brand = px.bar(
        brand_rev, y="brand_name", x="revenue", orientation="h",
        text="label",
        color="revenue",
        color_continuous_scale=["#1e3a5f", "#3b82f6", "#60a5fa"],
        labels={"revenue": "Revenue (₹)", "brand_name": "Brand"},
    )
    fig_brand.update_traces(textposition="outside", textfont_size=11)
    fig_brand.update_layout(
        template="plotly_dark", height=max(350, len(brand_rev) * 38),
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        margin=dict(l=10, r=80, t=20, b=30),
        showlegend=False, coloraxis_showscale=False,
        yaxis=dict(title=""),
    )
    st.plotly_chart(fig_brand, use_container_width=True)

    # Concentration metric
    top_3 = brand_rev.nlargest(3, "revenue")
    top_3_share = top_3["revenue"].sum() / brand_rev["revenue"].sum() * 100
    if top_3_share > 60:
        st.markdown(
            f'<div class="risk-box"><strong>Concentration Warning:</strong> Top 3 brands '
            f'({", ".join(top_3["brand_name"].tolist())}) account for '
            f'<strong>{top_3_share:.1f}%</strong> of total revenue. Portfolio is '
            f'over-concentrated.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="growth-box"><strong>Healthy Diversification:</strong> Top 3 brands '
            f'contribute {top_3_share:.1f}% — revenue is well-distributed.</div>',
            unsafe_allow_html=True,
        )

# ─── TAB 3: Risk Monitor ────────────────────────────────────────────────────
with tab_risk:
    st.markdown("### Revenue At Risk — SKUs Needing Attention")
    st.markdown(
        f'<div class="risk-box"><strong>Why it matters:</strong> SKUs with high review volume '
        f'but low rating (&lt;{rating_thresh}) are already being penalized by the marketplace '
        f'algorithm. High rating_count means the problem is entrenched — it takes many '
        f'positive reviews to move the needle. <strong>Action:</strong> Root-cause the reviews '
        f'(quality? shipping damage? expectation mismatch?), fix the issue, then run a '
        f'review-recovery campaign.</div>',
        unsafe_allow_html=True,
    )

    risky_display = risky[["item_id", "brand_name", "title", "revenue", "rating",
                           "rating_count"]].copy()
    risky_display["revenue"] = risky_display["revenue"].apply(fmt_inr)
    risky_display.columns = ["Item ID", "Brand", "Title", "Revenue", "Rating", "Review Count"]

    if len(risky_display):
        st.dataframe(risky_display, use_container_width=True, hide_index=True)
    else:
        st.success("No SKUs currently at risk with the selected filters.")

    # Declining SKUs (negative growth)
    st.markdown("### Declining SKUs (Negative 4W Growth)")
    declining = sku_merged[sku_merged["growth_pct"] < 0].sort_values("growth_pct")
    if len(declining):
        dec_display = declining[["item_id", "brand_name", "title", "revenue_latest",
                                 "revenue_4w", "growth_pct", "rating"]].copy()
        dec_display["revenue_latest"] = dec_display["revenue_latest"].apply(fmt_inr)
        dec_display["revenue_4w"] = dec_display["revenue_4w"].apply(fmt_inr)
        dec_display["growth_pct"] = dec_display["growth_pct"].apply(lambda v: f"{v:+.1f}%")
        dec_display.columns = ["Item ID", "Brand", "Title", "Rev (Latest)", "Rev (4W Ago)",
                               "4W Growth", "Rating"]
        st.dataframe(dec_display, use_container_width=True, hide_index=True)
        st.markdown(
            '<div class="risk-box"><strong>Action:</strong> For each declining SKU, check: '
            '(1) stock availability, (2) competitive price undercut, (3) ad spend changes, '
            '(4) search rank movement. Prioritize by absolute revenue loss.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.success("No declining SKUs in the selected period.")

# ─── TAB 4: Growth Drivers ──────────────────────────────────────────────────
with tab_growth:
    st.markdown("### High-Scaling SKUs — Growth Drivers")
    st.markdown(
        f'<div class="growth-box"><strong>Why it matters:</strong> These are SKUs with '
        f'&gt;{growth_thresh}% 4-week growth AND rating &ge; {rating_thresh}. They have '
        f'market traction AND customer approval — the best candidates for scaling. '
        f'<strong>Action:</strong> (1) Increase PPC budget, (2) Ensure 30+ days of inventory, '
        f'(3) Consider launching adjacent variants, (4) Protect the listing (A+ content, '
        f'review management).</div>',
        unsafe_allow_html=True,
    )

    if len(high_scaling):
        hs_display = high_scaling[["item_id", "brand_name", "title", "revenue_latest",
                                    "revenue_4w", "growth_pct", "rating",
                                    "rating_count"]].copy()
        hs_display = hs_display.sort_values("growth_pct", ascending=False)
        hs_display["revenue_latest"] = hs_display["revenue_latest"].apply(fmt_inr)
        hs_display["revenue_4w"] = hs_display["revenue_4w"].apply(fmt_inr)
        hs_display["growth_pct"] = hs_display["growth_pct"].apply(lambda v: f"{v:+.1f}%")
        hs_display.columns = ["Item ID", "Brand", "Title", "Rev (Latest)", "Rev (4W Ago)",
                               "4W Growth", "Rating", "Review Count"]
        st.dataframe(hs_display, use_container_width=True, hide_index=True)
    else:
        st.info("No SKUs meet the high-scaling criteria with current filter settings.")

    # Stars table: high revenue + positive growth + good rating
    stars_count = min(10, len(sku_merged[sku_merged["growth_pct"] > 0]))
    st.markdown(f"### Portfolio Stars (Top {stars_count} by Revenue with Positive Growth)")
    stars = sku_merged[
        sku_merged["growth_pct"] > 0
    ].nlargest(10, "revenue_latest")

    if len(stars):
        stars_disp = stars[["item_id", "brand_name", "title", "revenue_latest",
                            "growth_pct", "rating", "rating_count"]].copy()
        stars_disp["revenue_latest"] = stars_disp["revenue_latest"].apply(fmt_inr)
        stars_disp["growth_pct"] = stars_disp["growth_pct"].apply(lambda v: f"{v:+.1f}%")
        stars_disp.columns = ["Item ID", "Brand", "Title", "Revenue", "4W Growth",
                              "Rating", "Review Count"]
        st.dataframe(stars_disp, use_container_width=True, hide_index=True)

# ─── TAB 5: Trend Explorer ──────────────────────────────────────────────────
with tab_trend:
    st.markdown("### Revenue Trend Over Time")
    st.markdown(
        '<div class="insight-box"><strong>Why it matters:</strong> Weekly trend reveals '
        'seasonality, the impact of promotions, and whether growth is sustained or a spike. '
        '<strong>Action:</strong> Align inventory and ad budgets to seasonal patterns; '
        'investigate sudden drops for operational issues.</div>',
        unsafe_allow_html=True,
    )

    trend_items = st.multiselect(
        "Select SKUs to compare (leave empty for portfolio total)",
        options=sorted(filt["item_id"].unique()),
        default=[],
    )

    if trend_items:
        trend_data = filt[filt["item_id"].isin(trend_items)].copy()
        trend_agg = trend_data.groupby(["date", "item_id"])["revenue"].first().reset_index()
        fig_trend = px.line(
            trend_agg, x="date", y="revenue", color="item_id",
            labels={"date": "Date", "revenue": "Revenue (₹)", "item_id": "SKU"},
        )
    else:
        trend_agg = filt.groupby("date")["revenue"].sum().reset_index()
        fig_trend = px.area(
            trend_agg, x="date", y="revenue",
            labels={"date": "Date", "revenue": "Total Revenue (₹)"},
        )
        fig_trend.update_traces(fill="tozeroy", line_color="#3b82f6", fillcolor="rgba(59,130,246,0.15)")

    fig_trend.update_layout(
        template="plotly_dark", height=420,
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        margin=dict(l=40, r=20, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    # Price trend
    st.markdown("### Price Movement")
    price_trend = raw[
        raw["item_id"].isin(active_skus) & raw["brand_name"].isin(active_brands)
        & (raw["date"] >= date_start) & (raw["date"] <= date_end)
    ]
    if trend_items:
        price_trend = price_trend[price_trend["item_id"].isin(trend_items)]
    price_agg = price_trend.groupby("date")["price"].mean().reset_index()
    fig_price = px.line(price_agg, x="date", y="price",
                        labels={"date": "Date", "price": "Avg Price (₹)"})
    fig_price.update_traces(line_color="#f59e0b")
    fig_price.update_layout(
        template="plotly_dark", height=300,
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        margin=dict(l=40, r=20, t=20, b=40),
    )
    st.plotly_chart(fig_price, use_container_width=True)


# ── Footer ──────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    f"Data covers {raw['date'].min().strftime('%d %b %Y')} – "
    f"{LATEST_DATE.strftime('%d %b %Y')} · "
    f"{raw['item_id'].nunique()} SKUs across {raw['brand_name'].nunique()} brands · "
    f"Built for growth strategy review"
)
