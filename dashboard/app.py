"""Laguna Weather dashboard. Run from the repo root:  streamlit run dashboard/app.py

Read-only by design: it only SELECTs, through the same SQL files as the analysis
(sql/queries/*.sql and the rainy_seasons view), so dashboard and findings can't disagree.
On Streamlit Community Cloud, DATABASE_URL comes from the app's secrets and should be
the read-only dashboard_reader role.
"""

import datetime as dt
import os
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

# Streamlit puts dashboard/ on the import path, not the repo root; add the root
# so the pipeline package (and its single connection helper) can be imported.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.db import get_connection  # noqa: E402

TOWNS = ["San Pablo", "Calamba", "Santa Cruz", "Los Baños", "Biñan"]
SHARED_CELL = {"Calamba": "Los Baños", "Los Baños": "Calamba"}
CACHE_SECONDS = 3600  # data changes once a day; don't wake the database on every click

# Palette (validated: blue + orange pass every colour-blindness check in both modes).
# Light-mode orange is below 3:1 contrast on white, so its series are direct-labelled
# and every chart has a table view.
COLORS = {
    "light": {"series1": "#257de0", "series2": "#f47230", "muted": "#666666"},
    "dark":  {"series1": "#338ced", "series2": "#e76624", "muted": "#9c9c9c"},
}


# ---------- data ----------

def _use_streamlit_secret() -> None:
    """On Streamlit Cloud the URL is in st.secrets; locally it's in .env (read by db.py)."""
    try:
        if "DATABASE_URL" in st.secrets:
            os.environ.setdefault("DATABASE_URL", st.secrets["DATABASE_URL"])
    except FileNotFoundError:
        pass  # no secrets.toml locally: fine
    except Exception:  # StreamlitSecretNotFoundError in newer versions
        pass


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    _use_streamlit_secret()
    with get_connection() as conn:
        cur = conn.execute(sql, params or None)
        df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    # numeric columns from SQL arrive as Decimal; make them floats for charts
    for col in df.columns:
        if df[col].map(lambda v: type(v).__name__ == "Decimal").any():
            df[col] = df[col].astype(float)
    return df


def query_file(name: str) -> pd.DataFrame:
    return run_query((ROOT / "sql" / "queries" / name).read_text(encoding="utf-8"))


def theme_colors() -> dict:
    theme = getattr(getattr(st, "context", None), "theme", None)
    mode = getattr(theme, "type", None) or "light"
    return COLORS["dark" if mode == "dark" else "light"]


# ---------- sections ----------

def header() -> None:
    st.title("Is Laguna's rainy season shifting?")
    st.caption("Daily weather for five towns in Laguna, Philippines, 1991 to now. "
               "ERA5 reanalysis data via Open-Meteo, updated daily.")

    updated = run_query("""
        SELECT max(date) FILTER (WHERE precipitation_mm IS NOT NULL) AS newest_day,
               max(fetched_at) AS last_run
        FROM daily_weather""").iloc[0]
    last_run = pd.Timestamp(updated.last_run).tz_convert("Asia/Manila")
    st.markdown(
        f"**Data last updated:** newest day {updated.newest_day:%d %b %Y} · "
        f"pipeline last ran {last_run:%d %b %Y, %H:%M} PHT "
        "<span style='opacity:0.7'>(ERA5 publishes about a week behind)</span>",
        unsafe_allow_html=True,  # static text only; no user or database text here
    )


ALL_TOWNS = "All towns (4 grid cells)"


def answer_tiles() -> None:
    """The answer, before any scrolling: three tiles built from the trend queries."""
    season = query_file("season_trend.sql").set_index(["town", "measure"])
    rain = query_file("rain_trend.sql").set_index(["town", "measure"])
    onset, end = season.loc[(ALL_TOWNS, "onset")], season.loc[(ALL_TOWNS, "end")]
    dec_jan, annual = rain.loc[(ALL_TOWNS, "dec_jan_total")], rain.loc[(ALL_TOWNS, "annual_total")]

    # compare whole verdicts: "no clear trend" also contains the word "clear"
    timing_clear = onset.verdict != "no clear trend" or end.verdict != "no clear trend"
    tiles = [
        ("Rainy-season timing, 1991–2025",
         "Shifting" if timing_clear else "No clear shift",
         f"Starts ~{onset.average} ({onset.slope_per_decade:+.1f} days/decade), "
         f"ends ~{end.average} ({end.slope_per_decade:+.1f} days/decade). "
         f"Onset: {onset.verdict}; end: {end.verdict}."),
        ("December–January rain",
         f"{dec_jan.pct_per_decade:+.0f}% per decade",
         f"{dec_jan.slope_per_decade:+.0f} mm/decade on a {dec_jan.average:.0f} mm average: "
         f"{dec_jan.verdict}."),
        ("Annual rain",
         f"{annual.pct_per_decade:+.0f}% per decade",
         f"{annual.slope_per_decade:+.0f} mm/decade on a {annual.average:.0f} mm average: "
         f"{annual.verdict}."),
    ]
    for column, (label, value, detail) in zip(st.columns(3), tiles):
        with column, st.container(border=True):
            st.metric(label, value)
            st.caption(detail)
    st.caption("Laguna-wide: averaged over the four distinct ERA5 grid cells. "
               "\"Clear\" means the 95% range of the trend excludes zero.")


def town_picker() -> str:
    town = st.segmented_control("Town", TOWNS, default="San Pablo") or "San Pablo"
    if town in SHARED_CELL:
        st.caption(f"{town} and {SHARED_CELL[town]} fall in the same ~25 km ERA5 grid "
                   "cell, so their rain data is identical.")
    return town


# ---------- readable tables ----------

DATE = st.column_config.DateColumn(format="D MMM YYYY")
YEAR = st.column_config.NumberColumn(format="%d")


def _range(row) -> str:
    return f"{row.ci95_low:+.1f} to {row.ci95_high:+.1f}"


def readable_season_trends(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "Town": df.town,
        "Measure": df.measure.map({"onset": "Onset", "end": "End", "length": "Length"}),
        "Average": df.average,
        "Trend (days/decade)": df.slope_per_decade.map("{:+.1f}".format),
        "95% range": df.apply(_range, axis=1),
        "Robust trend (Sen)": df.sen_slope_per_decade.map("{:+.1f}".format),
        "Verdict": df.verdict,
    })
    return out


RAIN_MEASURES = {
    "annual_total": "Annual total (mm)", "season_total": "Rainy-season total (mm)",
    "dec_jan_total": "Dec–Jan total (mm)", "days_20mm_plus": "Days with 20+ mm",
    "wettest_day": "Wettest day (mm)",
}


def readable_rain_trends(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Town": df.town,
        "Measure": df.measure.map(RAIN_MEASURES),
        "Average": df.average.map("{:.1f}".format),
        "Trend per decade": df.slope_per_decade.map("{:+.1f}".format),
        "% per decade": df.pct_per_decade.map("{:+.0f}%".format),
        "95% range": df.apply(_range, axis=1),
        "Robust trend (Sen)": df.sen_slope_per_decade.map("{:+.1f}".format),
        "Verdict": df.verdict,
    })


def latest_report() -> None:
    st.caption("Posted to Discord every Monday. Numbers are computed in SQL; the summary is "
               "written by an LLM and checked against them before posting.")
    report = run_query("""
        SELECT week_start, summary_text, model, posted_at
        FROM reports WHERE posted_at IS NOT NULL
        ORDER BY week_start DESC LIMIT 1""")
    if report.empty:
        st.info("No weekly report has been posted yet.")
        return
    with st.container(border=True):
        # The text is our own generated report (validated numbers); render as markdown
        # but never as HTML.
        st.markdown(report.iloc[0].summary_text)


def recent_weather(town: str, colors: dict) -> None:
    st.subheader(f"Last 90 days in {town}")
    df = query_file("recent_days.sql")
    df = df[df.town == town].copy()
    df["date"] = pd.to_datetime(df.date)

    left, right = st.columns(2)
    with left:
        st.markdown("**Rain (mm)**")
        bars = alt.Chart(df).mark_bar(color=colors["series1"], cornerRadiusTopLeft=2,
                                      cornerRadiusTopRight=2).encode(
            x=alt.X("date:T", title=None, axis=alt.Axis(format="%d %b")),
            y=alt.Y("precipitation_mm:Q", title="mm"),
            tooltip=[alt.Tooltip("date:T", title="Date", format="%d %b %Y"),
                     alt.Tooltip("precipitation_mm:Q", title="Rain that day (mm)", format=".1f"),
                     alt.Tooltip("rain_7d_mm:Q", title="7-day total (mm)", format=".1f")],
        )
        line = alt.Chart(df).mark_line(color=colors["series2"], strokeWidth=2).encode(
            x="date:T", y="rain_7d_mm:Q")
        last = df.tail(1)
        line_label = alt.Chart(last).mark_text(align="left", dx=4, color=colors["muted"]).encode(
            x="date:T", y="rain_7d_mm:Q", text=alt.value("7-day total"))
        bar_label = alt.Chart(df.nlargest(1, "precipitation_mm")).mark_text(
            dy=-8, color=colors["muted"]).encode(
            x="date:T", y="precipitation_mm:Q", text=alt.value("daily rain"))
        st.altair_chart((bars + line + line_label + bar_label).properties(height=280),
                        width="stretch")

    with right:
        st.markdown("**Temperature (°C)**")
        long = df.melt(id_vars="date", value_vars=["temp_max_c", "temp_min_c"],
                       var_name="series", value_name="celsius")
        long["series"] = long.series.map({"temp_max_c": "Daily high", "temp_min_c": "Daily low"})
        color = alt.Color("series:N", title=None, legend=alt.Legend(orient="top"),
                          scale=alt.Scale(domain=["Daily high", "Daily low"],
                                          range=[colors["series2"], colors["series1"]]))
        nearest = alt.selection_point(nearest=True, on="pointerover", fields=["date"], empty=False)
        lines = alt.Chart(long).mark_line(strokeWidth=2).encode(
            x=alt.X("date:T", title=None, axis=alt.Axis(format="%d %b")),
            y=alt.Y("celsius:Q", title="°C", scale=alt.Scale(zero=False)),
            color=color)
        hover = alt.Chart(df).mark_rule(color=colors["muted"]).encode(
            x="date:T", opacity=alt.condition(nearest, alt.value(0.5), alt.value(0)),
            tooltip=[alt.Tooltip("date:T", title="Date", format="%d %b %Y"),
                     alt.Tooltip("temp_max_c:Q", title="High (°C)", format=".1f"),
                     alt.Tooltip("temp_min_c:Q", title="Low (°C)", format=".1f")],
        ).add_params(nearest)
        ends = alt.Chart(long[long.date == long.date.max()]).mark_text(
            align="left", dx=4, color=colors["muted"]).encode(
            x="date:T", y="celsius:Q", text="series:N")
        st.altair_chart((lines + hover + ends).properties(height=280), width="stretch")

    with st.expander("Show the data as a table"):
        st.dataframe(
            df[["date", "precipitation_mm", "rain_7d_mm", "temp_max_c", "temp_min_c"]]
            .rename(columns={"date": "Date", "precipitation_mm": "Rain (mm)",
                             "rain_7d_mm": "7-day rain (mm)", "temp_max_c": "High (°C)",
                             "temp_min_c": "Low (°C)"})
            .sort_values("Date", ascending=False),
            hide_index=True, width="stretch",
            column_config={"Date": DATE,
                           **{c: st.column_config.NumberColumn(format="%.1f")
                              for c in ["Rain (mm)", "7-day rain (mm)", "High (°C)", "Low (°C)"]}})


def rainy_seasons(town: str, colors: dict) -> None:
    st.subheader(f"Rainy season in {town}, year by year")
    seasons = query_file("rainy_season.sql")
    seasons = seasons[seasons.town == town].copy()
    # place every season on one shared calendar (1 Feb 2001 - 31 Jan 2002) so years line up
    base = pd.Timestamp("2001-02-01")
    seasons["start"] = base + pd.to_timedelta(seasons.onset_day, unit="D")
    seasons["finish"] = base + pd.to_timedelta(seasons.end_day, unit="D")
    seasons["year_label"] = seasons.year.astype(str)
    typical = seasons.iloc[0]

    trend = query_file("season_trend.sql")
    t = trend[trend.town == town].set_index("measure")

    bars = alt.Chart(seasons).mark_bar(color=colors["series1"], height=6, cornerRadius=3).encode(
        x=alt.X("start:T", title=None, scale=alt.Scale(domain=["2001-02-01", "2002-01-31"]),
                axis=alt.Axis(format="%b")),
        x2="finish:T",
        y=alt.Y("year_label:O", title=None, sort="descending"),
        tooltip=[alt.Tooltip("year:O", title="Season"),
                 alt.Tooltip("onset_date:T", title="Onset", format="%d %b %Y"),
                 alt.Tooltip("end_date:T", title="End", format="%d %b %Y"),
                 alt.Tooltip("length_days:Q", title="Length (days)")],
    )
    refs = pd.DataFrame({"when": [pd.Timestamp(typical.typical_onset), pd.Timestamp(typical.typical_end)],
                         "label": ["typical onset", "typical end"]})
    rules = alt.Chart(refs).mark_rule(color=colors["muted"], strokeWidth=1).encode(x="when:T")
    rule_labels = alt.Chart(refs).mark_text(align="left", dx=4, dy=-4, baseline="bottom",
                                            color=colors["muted"]).encode(
        x="when:T", y=alt.value(0), text="label:N")
    st.altair_chart((bars + rules + rule_labels).properties(height=520), width="stretch")

    st.markdown(
        f"Typical season: **{typical.typical_onset:%d %b} to {typical.typical_end:%d %b}**. "
        f"Onset trend **{t.loc['onset', 'slope_per_decade']:+.1f} days/decade** "
        f"(95% range {t.loc['onset', 'ci95_low']:+.1f} to {t.loc['onset', 'ci95_high']:+.1f}): "
        f"{t.loc['onset', 'verdict']}. End trend **{t.loc['end', 'slope_per_decade']:+.1f} days/decade** "
        f"({t.loc['end', 'ci95_low']:+.1f} to {t.loc['end', 'ci95_high']:+.1f}): {t.loc['end', 'verdict']}."
    )
    with st.expander("Show the data as a table"):
        st.dataframe(
            seasons[["year", "onset_date", "end_date", "length_days"]]
            .rename(columns={"year": "Season", "onset_date": "Onset", "end_date": "End",
                             "length_days": "Length (days)"})
            .sort_values("Season", ascending=False),
            hide_index=True, width="stretch",
            column_config={"Season": YEAR, "Onset": DATE, "End": DATE})


def dec_jan_rain(town: str, colors: dict) -> None:
    st.subheader(f"December–January rain in {town}")
    df = query_file("dec_jan_rain_by_year.sql")
    df = df[df.town == town]
    rt = query_file("rain_trend.sql")
    r = rt[(rt.town == town) & (rt.measure == "dec_jan_total")].iloc[0]

    bars = alt.Chart(df).mark_bar(color=colors["series1"], cornerRadiusTopLeft=2,
                                  cornerRadiusTopRight=2).encode(
        x=alt.X("year:O", title="December of year (with the following January)",
                axis=alt.Axis(labelAngle=0, values=list(range(1991, 2026, 5)))),
        y=alt.Y("dec_jan_mm:Q", title="mm"),
        tooltip=[alt.Tooltip("year:O", title="Dec of"),
                 alt.Tooltip("dec_jan_mm:Q", title="Dec–Jan rain (mm)", format=".1f"),
                 alt.Tooltip("trend_mm:Q", title="Trend line (mm)", format=".1f")],
    )
    line = alt.Chart(df).mark_line(color=colors["series2"], strokeWidth=2).encode(
        x="year:O", y="trend_mm:Q")
    label = alt.Chart(df.tail(1)).mark_text(align="right", dy=-8, color=colors["muted"]).encode(
        x="year:O", y="trend_mm:Q", text=alt.value("trend"))
    st.altair_chart((bars + line + label).properties(height=300), width="stretch")
    st.markdown(
        f"Average **{r.average:.0f} mm**. Trend **{r.slope_per_decade:+.1f} mm/decade** "
        f"({r.pct_per_decade:+.0f}% per decade; 95% range {r.ci95_low:+.1f} to {r.ci95_high:+.1f}): "
        f"{r.verdict}."
    )
    with st.expander("Show the data as a table"):
        st.dataframe(
            df[["year", "dec_jan_mm", "trend_mm"]]
            .rename(columns={"year": "December of", "dec_jan_mm": "Dec–Jan rain (mm)",
                             "trend_mm": "Trend line (mm)"})
            .sort_values("December of", ascending=False),
            hide_index=True, width="stretch",
            column_config={"December of": YEAR,
                           "Dec–Jan rain (mm)": st.column_config.NumberColumn(format="%.1f"),
                           "Trend line (mm)": st.column_config.NumberColumn(format="%.1f")})


def findings() -> None:
    st.subheader("Findings for Laguna, 1991–2025")
    st.caption("Averaged over the four distinct grid cells (Calamba and Los Baños share one). "
               "Numbers come straight from sql/queries/season_trend.sql and rain_trend.sql.")
    st_ = query_file("season_trend.sql").set_index(["town", "measure"])
    rt = query_file("rain_trend.sql").set_index(["town", "measure"])
    on, end = st_.loc[(ALL_TOWNS, "onset")], st_.loc[(ALL_TOWNS, "end")]
    dj, ann = rt.loc[(ALL_TOWNS, "dec_jan_total")], rt.loc[(ALL_TOWNS, "annual_total")]

    def rng(row):
        return f"95% range {row.ci95_low:+.1f} to {row.ci95_high:+.1f}"

    st.markdown(
        f"1. **Season timing.** Onset averages {on.average}, trend {on.slope_per_decade:+.1f} "
        f"days/decade ({rng(on)}): *{on.verdict}*. The end averages {end.average}, trend "
        f"{end.slope_per_decade:+.1f} days/decade ({rng(end)}): *{end.verdict}*.\n"
        f"2. **December–January rain.** {dj.pct_per_decade:+.0f}% per decade "
        f"({dj.slope_per_decade:+.1f} mm/decade on a {dj.average:.0f} mm average; {rng(dj)}): "
        f"*{dj.verdict}*.\n"
        f"3. **Annual rain.** {ann.pct_per_decade:+.0f}% per decade "
        f"({ann.slope_per_decade:+.1f} mm/decade on {ann.average:.0f} mm; {rng(ann)}): *{ann.verdict}*."
    )
    st.markdown("**Season timing, every town**")
    st.dataframe(readable_season_trends(query_file("season_trend.sql")),
                 hide_index=True, width="stretch")
    st.markdown("**Rain amounts, every town**")
    st.dataframe(readable_rain_trends(query_file("rain_trend.sql")),
                 hide_index=True, width="stretch")


def method_and_limits() -> None:
    st.markdown(
        "- **Data:** ERA5 reanalysis (a weather model's reconstruction on a ~25 km grid) "
        "via Open-Meteo, the same model for every year. Not rain-gauge readings.\n"
        "- **Season dates:** anomalous accumulation (Liebmann & Marengo, 2001): onset is where "
        "the running total of (daily rain − the town's average) bottoms out; the end is where "
        "it peaks. Search windows are this project's own choice.\n"
        "- **Check against PAGASA:** onsets land a median 6 days before PAGASA's declared "
        "dates (2016–2024). PAGASA's declaration is national, so this is a sanity check.\n"
        "- **Trends:** least-squares slope with a 95% confidence interval, plus Sen's slope "
        "as a robustness check. \"No clear trend\" means the range includes zero.\n"
        "- Code and SQL: the project's GitHub repository."
    )


def main() -> None:
    st.set_page_config(page_title="Laguna Weather", page_icon="🌧️", layout="wide")
    colors = theme_colors()
    header()
    answer_tiles()

    overview, explore, report, method = st.tabs(
        ["Overview", "Explore a town", "Weekly report", "Method & limits"])
    with overview:
        findings()
    with explore:
        town = town_picker()
        recent_weather(town, colors)
        rainy_seasons(town, colors)
        dec_jan_rain(town, colors)
    with report:
        latest_report()
    with method:
        method_and_limits()


main()
