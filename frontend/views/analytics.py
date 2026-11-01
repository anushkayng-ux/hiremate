import altair as alt
import pandas as pd
import streamlit as st

import api
import ui

ui.header("Reports", sub="How hiring is going.")
a = ui.safe(api.get, "/analytics")
if not a:
    st.stop()

GREEN, GOLD, CREAM = "#0E7A5C", "#2B2350", "#D9D6E6"
r = a["rates"]
cols = st.columns(4)
for col, (label, val) in zip(cols, [("Shortlist rate", f"{r['shortlist_rate']}%"), ("Interviews done", r["interviews_done"]),
                                    ("Selected", r["selected"]), ("Rejected", r["rejected"])]):
    with col.container(border=True):
        ui.html_block(f'<div class="kpi">{val}</div><div class="kpil">{label}</div>')


def bar(df, x, y, color=GREEN, horizontal=False, fmt=None):
    enc = dict(x=alt.X(f"{x}:Q", title=None, axis=alt.Axis(format="d", tickMinStep=1)), y=alt.Y(f"{y}:N", sort="-x", title=None)) if horizontal else \
        dict(x=alt.X(f"{x}:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)), y=alt.Y(f"{y}:Q", title=None))
    return alt.Chart(df).mark_bar(color=color, cornerRadius=3).encode(**enc, tooltip=list(df.columns)).properties(height=240)


left, right = st.columns(2, gap="large")
with left:
    st.markdown("**Pipeline funnel**")
    st.altair_chart(bar(pd.DataFrame(a["funnel"]), "count", "stage", horizontal=True).encode(
        y=alt.Y("stage:N", sort=None, title=None)), width="stretch")
    st.markdown("**Average match by job**")
    st.altair_chart(bar(pd.DataFrame(a["by_job"]), "job", "avg_match", GOLD), width="stretch")
with right:
    st.markdown("**Applications by job**")
    st.altair_chart(bar(pd.DataFrame(a["by_job"]), "job", "applications"), width="stretch")
    st.markdown("**Most-missing must-have skills**")
    if a["missing_skills"]:
        st.altair_chart(bar(pd.DataFrame(a["missing_skills"]), "count", "skill", GOLD, horizontal=True),
                        width="stretch")
    else:
        st.caption("No gaps.")

# ---------------------------------------------------------------- speed, sources, offers
mx = ui.safe(api.get, "/x/metrics") or {}
st.markdown("### Speed and sources")
o = mx.get("offers", {})
fmt_d = lambda v: f"{v:g} days" if v is not None else "No hires yet"
cols = st.columns(4)
for col, (label, val) in zip(cols, [("Time to hire (applied → hired)", fmt_d(mx.get("time_to_hire_days"))),
                                    ("Time to interview", fmt_d(mx.get("time_to_interview_days"))),
                                    ("Offers sent", o.get("sent", 0)),
                                    ("Offer acceptance", f"{o['acceptance_rate']}%" if o.get("acceptance_rate") is not None
                                     else "No answers yet")]):
    with col.container(border=True):
        ui.html_block(f'<div class="kpi" style="font-size:1.5rem">{val}</div><div class="kpil">{label}</div>')
l2, r2 = st.columns(2, gap="large")
with l2:
    st.markdown("**Where good candidates come from**")
    if mx.get("by_source"):
        df = pd.DataFrame(mx["by_source"])
        base = alt.Chart(df).encode(y=alt.Y("source:N", sort="-x", title=None))
        st.altair_chart((base.mark_bar(color=CREAM, cornerRadius=3).encode(x=alt.X("applications:Q", title="Applications"))
                         + base.mark_bar(color=GREEN, cornerRadius=3, height=8).encode(
                             x="shortlisted:Q", tooltip=["source", "applications", "shortlisted", "hired", "quality"]))
                        .properties(height=240), width="stretch")
        st.caption("Grey = applications, green = shortlisted or further. Spend more on sources with a long green bar.")
with r2:
    st.markdown("**Average days people wait in each stage**")
    if mx.get("days_in_stage"):
        st.altair_chart(bar(pd.DataFrame(mx["days_in_stage"]), "stage", "days", GOLD), width="stretch")
        st.caption("Long waits lose good people. The target for each stage is 3 days.")
if mx.get("referrals"):
    st.markdown("**Employee referrals**")
    for rf in mx["referrals"]:
        ui.html_block(f'<span class="small"><b>{ui.esc(rf["referred_by"] or "Unknown")}</b> referred '
                      f'{ui.esc(rf["name"])} for {ui.esc(rf["title"])} · {ui.esc(ui.LABEL.get(rf["stage"], rf["stage"]))}</span>')
if mx.get("jobs_open"):
    st.caption("Days each job has been open: " + " · ".join(f'{j["job"]} {j["days_open"]}' for j in mx["jobs_open"]))

st.markdown("**Talent groups** · K-Means on CV text, drawn with PCA")
tg = a["talent_groups"]
if tg["points"]:
    df = pd.DataFrame(tg["points"])
    df["group"] = df["group"].astype(str)
    df["name"] = [ui.name(n, i) for n, i in zip(df["name"], df["id"])]
    pts = alt.Chart(df).mark_circle(size=160).encode(
        x=alt.X("x:Q", axis=None), y=alt.Y("y:Q", axis=None),
        color=alt.Color("group:N", scale=alt.Scale(range=[GREEN, GOLD, "#0E7A5C", "#9333EA"]), title="Group"),
        tooltip=["name", "group"])
    labels = pts.mark_text(dy=-12, fontSize=11, color="#1E1B33").encode(text="name")
    st.altair_chart((pts + labels).properties(height=300), width="stretch")
    st.caption(" · ".join(f"Group {g['group']}: {', '.join(g['top_terms'])}" for g in tg["groups"]))
st.caption(f"Logistic regression (shortlist chance) training accuracy: "
           f"{round(a['model']['logistic_regression_train_accuracy'] * 100)}% on the small example history. "
           "Treat ML outputs as hints; recruiters decide.")
