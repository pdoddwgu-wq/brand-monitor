import json
import sqlite3

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import DB_PATH, SCHOOLS

st.set_page_config(
    page_title="University Brand Monitor",
    page_icon="🎓",
    layout="wide",
)

SCHOOL_LABELS = {k: v["short"] for k, v in SCHOOLS.items()}
SENTIMENT_COLORS = {
    "positive": "#2ecc71",
    "negative": "#e74c3c",
    "neutral": "#95a5a6",
    "mixed": "#f39c12",
}


@st.cache_data(ttl=180)
def load_data() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT
            m.id, m.school_key, m.source, m.url,
            m.title, m.body, m.score AS upvotes,
            m.rating, m.created_at, m.fetched_at,
            s.sentiment, s.score AS sentiment_score,
            s.themes, s.programs, s.is_citation, s.summary
        FROM mentions m
        INNER JOIN sentiment s ON m.id = s.mention_id
        """,
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=180)
def load_counts() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT school_key, source, COUNT(*) AS n, SUM(is_analyzed) AS analyzed "
        "FROM mentions GROUP BY school_key, source",
        conn,
    )
    conn.close()
    return df


# ── Header (title only — date range added below after data loads) ─────────────
st.title("University Brand Monitor")

try:
    df = load_data()
except Exception:
    st.warning("No analyzed data yet. Run `python main.py crawl` then `python main.py analyze`.")
    st.stop()

if df.empty:
    st.info("Crawl and analysis complete but the results table is empty — check your run.")
    st.stop()

df["school_label"] = df["school_key"].map(SCHOOL_LABELS)
df["created_at_dt"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
df["date"] = df["created_at_dt"].dt.date

# ── Date range ────────────────────────────────────────────────────────────────
dated_only = df["created_at_dt"].dropna()
if not dated_only.empty:
    data_start = dated_only.min()
    data_end   = dated_only.max()
    date_range_str = f"{data_start.strftime('%B %d, %Y')} — {data_end.strftime('%B %d, %Y')}"
    dated_count   = len(dated_only)
    undated_count = df["created_at_dt"].isna().sum()
else:
    date_range_str = "No dated mentions"
    dated_count    = 0
    undated_count  = len(df)

col_h1, col_h2 = st.columns([3, 2])
col_h1.caption("WGU vs SNHU · GCU · Purdue Global · University of Phoenix")
col_h2.caption(f"📅 Data covers: **{date_range_str}**")

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")

    all_sources = sorted(df["source"].unique().tolist())
    sel_sources = st.multiselect("Source", all_sources, default=all_sources)

    all_schools = [SCHOOL_LABELS[k] for k in SCHOOLS if SCHOOL_LABELS[k] in df["school_label"].unique()]
    sel_schools = st.multiselect("School", all_schools, default=all_schools)

    sel_sentiment = st.multiselect(
        "Sentiment",
        ["positive", "negative", "neutral", "mixed"],
        default=["positive", "negative", "neutral", "mixed"],
    )

    citations_only = st.checkbox("Citations only")

    st.divider()
    st.caption("Reload counts")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

filtered = df[
    df["source"].isin(sel_sources)
    & df["school_label"].isin(sel_schools)
    & df["sentiment"].isin(sel_sentiment)
]
if citations_only:
    filtered = filtered[filtered["is_citation"] == 1]

# ── Top KPIs ──────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Mentions", f"{len(filtered):,}")
k2.metric("Positive", f"{(filtered['sentiment'] == 'positive').mean():.0%}")
k3.metric("Negative", f"{(filtered['sentiment'] == 'negative').mean():.0%}")
k4.metric("Avg Score", f"{filtered['sentiment_score'].mean():.2f}")
k5.metric("Citations", f"{int(filtered['is_citation'].sum()):,}")

if not dated_only.empty:
    st.info(
        f"📅 **Data timeline:** {date_range_str}  "
        f"·  {dated_count:,} dated mentions"
        + (f"  ·  {undated_count:,} undated (no timestamp available)" if undated_count else "")
    )

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_overview, tab_themes, tab_programs, tab_timeline, tab_citations, tab_mentions = st.tabs(
    ["Overview", "Themes", "Programs", "Timeline", "Citations", "Mentions"]
)

# ── Overview ──────────────────────────────────────────────────────────────────
with tab_overview:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Avg Sentiment Score")
        avg = (
            filtered.groupby("school_label")["sentiment_score"]
            .mean()
            .reset_index()
            .sort_values("sentiment_score")
        )
        fig = px.bar(
            avg,
            x="sentiment_score",
            y="school_label",
            orientation="h",
            color="sentiment_score",
            color_continuous_scale="RdYlGn",
            range_color=[-1, 1],
            labels={"sentiment_score": "Score", "school_label": ""},
        )
        fig.update_layout(height=280, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Sentiment Mix")
        breakdown = (
            filtered.groupby(["school_label", "sentiment"])
            .size()
            .reset_index(name="count")
        )
        fig2 = px.bar(
            breakdown,
            x="school_label",
            y="count",
            color="sentiment",
            barmode="stack",
            color_discrete_map=SENTIMENT_COLORS,
            labels={"school_label": "", "count": "Mentions"},
        )
        fig2.update_layout(height=280, legend_title="")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Source Breakdown")
    source_breakdown = (
        filtered.groupby(["school_label", "source"])
        .size()
        .reset_index(name="count")
    )
    fig3 = px.bar(
        source_breakdown,
        x="school_label",
        y="count",
        color="source",
        barmode="group",
        labels={"school_label": "", "count": "Mentions"},
    )
    fig3.update_layout(height=260, legend_title="Source")
    st.plotly_chart(fig3, use_container_width=True)

# ── Themes ────────────────────────────────────────────────────────────────────
with tab_themes:
    # Explode the themes JSON array into rows
    theme_rows = []
    for _, row in filtered.iterrows():
        try:
            themes = json.loads(row["themes"]) if row["themes"] else []
        except (json.JSONDecodeError, TypeError):
            themes = []
        for t in themes:
            theme_rows.append(
                {
                    "school": row["school_label"],
                    "theme": t.lower().strip(),
                    "sentiment": row["sentiment"],
                }
            )

    if not theme_rows:
        st.info("No theme data available.")
    else:
        theme_df = pd.DataFrame(theme_rows)
        top_themes = theme_df["theme"].value_counts().head(15).index.tolist()
        theme_df = theme_df[theme_df["theme"].isin(top_themes)]

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Theme Frequency Heatmap (by school)")
            pivot = (
                theme_df.groupby(["school", "theme"])
                .size()
                .reset_index(name="n")
                .pivot(index="school", columns="theme", values="n")
                .fillna(0)
            )
            fig4 = px.imshow(
                pivot,
                color_continuous_scale="Blues",
                aspect="auto",
                labels={"color": "Mentions"},
            )
            fig4.update_layout(height=320)
            st.plotly_chart(fig4, use_container_width=True)

        with col2:
            st.subheader("Top Themes – Sentiment Split")
            theme_sent = (
                theme_df.groupby(["theme", "sentiment"])
                .size()
                .reset_index(name="count")
            )
            fig5 = px.bar(
                theme_sent,
                x="count",
                y="theme",
                color="sentiment",
                orientation="h",
                barmode="stack",
                color_discrete_map=SENTIMENT_COLORS,
                labels={"theme": "", "count": "Mentions"},
            )
            fig5.update_layout(height=360, legend_title="")
            st.plotly_chart(fig5, use_container_width=True)

# ── Programs ─────────────────────────────────────────────────────────────────
with tab_programs:
    prog_rows = []
    for _, row in filtered.iterrows():
        try:
            programs = json.loads(row["programs"]) if row["programs"] else []
        except (json.JSONDecodeError, TypeError):
            programs = []
        for p in programs:
            prog_rows.append({
                "school": row["school_label"],
                "program": p,
                "sentiment": row["sentiment"],
                "score": row["sentiment_score"],
                "source": row["source"],
                "url": row["url"],
                "summary": row["summary"],
            })

    if not prog_rows:
        st.info("No program mentions detected yet. Run `python3 main.py analyze` to tag programs.")
    else:
        prog_df = pd.DataFrame(prog_rows)

        # Top KPIs
        p1, p2, p3 = st.columns(3)
        p1.metric("Program Mentions", f"{len(prog_df):,}")
        p2.metric("Unique Programs", prog_df["program"].nunique())
        p3.metric("Avg Sentiment", f"{prog_df['score'].mean():.2f}")

        st.divider()
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Most Discussed Programs")
            top_progs = (
                prog_df.groupby("program")
                .size()
                .reset_index(name="mentions")
                .sort_values("mentions", ascending=True)
                .tail(15)
            )
            fig_p1 = px.bar(
                top_progs, x="mentions", y="program", orientation="h",
                labels={"mentions": "Mentions", "program": ""},
                color="mentions", color_continuous_scale="Blues",
            )
            fig_p1.update_layout(height=420, coloraxis_showscale=False)
            st.plotly_chart(fig_p1, use_container_width=True)

        with col2:
            st.subheader("Avg Sentiment by Program")
            prog_sent = (
                prog_df.groupby("program")["score"]
                .mean()
                .reset_index()
                .sort_values("score", ascending=True)
                .tail(15)
            )
            fig_p2 = px.bar(
                prog_sent, x="score", y="program", orientation="h",
                color="score", color_continuous_scale="RdYlGn",
                range_color=[-1, 1],
                labels={"score": "Avg Sentiment", "program": ""},
            )
            fig_p2.update_layout(height=420, coloraxis_showscale=False)
            st.plotly_chart(fig_p2, use_container_width=True)

        st.subheader("Program Mentions by School")
        top_prog_names = prog_df["program"].value_counts().head(12).index.tolist()
        prog_school = (
            prog_df[prog_df["program"].isin(top_prog_names)]
            .groupby(["program", "school"])
            .size()
            .reset_index(name="mentions")
        )
        fig_p3 = px.bar(
            prog_school, x="program", y="mentions", color="school",
            barmode="group",
            labels={"program": "", "mentions": "Mentions", "school": "School"},
        )
        fig_p3.update_layout(height=360, xaxis_tickangle=-30, legend_title="")
        st.plotly_chart(fig_p3, use_container_width=True)

        st.subheader("Sentiment Heatmap — Program × School")
        heat_data = (
            prog_df[prog_df["program"].isin(top_prog_names)]
            .groupby(["program", "school"])["score"]
            .mean()
            .reset_index()
            .pivot(index="program", columns="school", values="score")
            .fillna(0)
        )
        fig_p4 = px.imshow(
            heat_data, color_continuous_scale="RdYlGn",
            range_color=[-1, 1], aspect="auto",
            labels={"color": "Avg Sentiment"},
        )
        fig_p4.update_layout(height=380)
        st.plotly_chart(fig_p4, use_container_width=True)

        st.subheader("Program Mentions Detail")
        prog_sel = st.selectbox("Filter by program", ["All"] + sorted(prog_df["program"].unique().tolist()))
        prog_display = prog_df if prog_sel == "All" else prog_df[prog_df["program"] == prog_sel]
        prog_display = prog_display.copy()
        prog_display.loc[prog_display["school"] == "UoPX", "summary"] = ""
        prog_display.loc[prog_display["school"] == "UoPX", "url"] = ""
        st.dataframe(
            prog_display[["school", "program", "sentiment", "score", "summary", "url"]].rename(
                columns={"school": "School", "program": "Program", "sentiment": "Sentiment",
                         "score": "Score", "summary": "Summary", "url": "Source"}
            ).sort_values("Score"),
            use_container_width=True,
            height=350,
            column_config={
                "Source": st.column_config.LinkColumn("Source", display_text="View →"),
                "Score": st.column_config.NumberColumn(format="%.2f"),
            },
        )

# ── Timeline ──────────────────────────────────────────────────────────────────
with tab_timeline:
    timed = filtered.dropna(subset=["date"]).copy()
    if timed.empty:
        st.info("No timestamped data yet (Trustpilot and Reddit posts carry dates).")
    else:
        st.subheader("Avg Sentiment Over Time")
        daily = (
            timed.groupby(["date", "school_label"])["sentiment_score"]
            .mean()
            .reset_index()
        )
        fig6 = px.line(
            daily,
            x="date",
            y="sentiment_score",
            color="school_label",
            labels={"sentiment_score": "Avg Sentiment", "date": "Date", "school_label": "School"},
            markers=True,
        )
        fig6.update_layout(height=380, legend_title="")
        st.plotly_chart(fig6, use_container_width=True)

        st.subheader("Mention Volume Over Time")
        vol = timed.groupby(["date", "school_label"]).size().reset_index(name="mentions")
        fig7 = px.area(
            vol,
            x="date",
            y="mentions",
            color="school_label",
            labels={"mentions": "Mentions", "date": "Date", "school_label": "School"},
        )
        fig7.update_layout(height=320, legend_title="")
        st.plotly_chart(fig7, use_container_width=True)

# ── Citations ─────────────────────────────────────────────────────────────────
with tab_citations:
    cites = filtered[filtered["is_citation"] == 1].copy()
    st.metric("Citations in current filter", len(cites))

    if cites.empty:
        st.info("No citations match the current filters.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            cit_school = (
                cites.groupby(["school_label", "sentiment"])
                .size()
                .reset_index(name="count")
            )
            fig8 = px.bar(
                cit_school,
                x="school_label",
                y="count",
                color="sentiment",
                barmode="stack",
                color_discrete_map=SENTIMENT_COLORS,
                title="Citations by School",
                labels={"school_label": "", "count": "Citations"},
            )
            fig8.update_layout(height=300, legend_title="")
            st.plotly_chart(fig8, use_container_width=True)

        with col2:
            cit_src = (
                cites.groupby("source")
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
            )
            fig9 = px.pie(
                cit_src,
                names="source",
                values="count",
                title="Citation Sources",
                hole=0.4,
            )
            fig9.update_layout(height=300)
            st.plotly_chart(fig9, use_container_width=True)

        cites_display = cites.copy()
        cites_display.loc[cites_display["school_label"] == "UoPX", "summary"] = ""
        cites_display.loc[cites_display["school_label"] == "UoPX", "url"] = ""
        st.dataframe(
            cites_display[["school_label", "source", "sentiment", "summary", "url"]].rename(
                columns={"school_label": "School", "source": "Source",
                         "sentiment": "Sentiment", "summary": "Summary", "url": "Link"}
            ),
            use_container_width=True,
            height=400,
            column_config={"Link": st.column_config.LinkColumn()},
        )

# ── Mentions ──────────────────────────────────────────────────────────────────
with tab_mentions:
    st.subheader(f"All Mentions ({len(filtered):,})")
    display = filtered[
        ["school_label", "source", "sentiment", "sentiment_score", "summary", "url", "created_at"]
    ].rename(
        columns={
            "school_label": "School",
            "source": "Source",
            "sentiment": "Sentiment",
            "sentiment_score": "Score",
            "summary": "Summary",
            "url": "Link",
            "created_at": "Date",
        }
    ).sort_values("Score")

    st.dataframe(
        display,
        use_container_width=True,
        height=520,
        column_config={
            "Link": st.column_config.LinkColumn(),
            "Score": st.column_config.NumberColumn(format="%.2f"),
        },
    )
