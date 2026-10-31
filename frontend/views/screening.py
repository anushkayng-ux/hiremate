import streamlit as st

import api
import ui
import widgets

ui.header("Screening & Matching", "Review")
jobs = ui.safe(api.get, "/jobs", status="Open") or []
if not jobs:
    st.info("No open jobs.")
    st.stop()
ids = [j["id"] for j in jobs]
default = st.session_state.get("job_id") if st.session_state.get("job_id") in ids else ids[0]
a, b = st.columns([2, 2], vertical_alignment="bottom")
jid = a.selectbox("Job", ids, index=ids.index(default), format_func=lambda i: next(j["title"] for j in jobs if j["id"] == i))
scope = b.segmented_control("Who", ["Applicants", "Whole talent pool"], default="Applicants")
st.session_state.job_id = jid
res = ui.safe(api.get, f"/match/job/{jid}", scope="all" if scope == "Whole talent pool" else "pool") or []
job = next(j for j in jobs if j["id"] == jid)

st.caption(f"Must-haves: {', '.join(job['must'])} · {job['min_years']:g}+ years. "
           "Tick 2–3 people to compare them side by side.")
picked = []
for r in res:
    with st.container(border=True):
        x, y, z, w = st.columns([0.35, 2.6, 4, 1], vertical_alignment="center")
        if x.checkbox(" ", key=f"pk{jid}-{r['candidate_id']}", label_visibility="collapsed"):
            picked.append(r["candidate_id"])
        y.markdown(f'<b>{ui.esc(ui.name(r["name"], r["candidate_id"]))}</b> {ui.score_chip(r["score"])}<br>'
                   f'<span class="muted small">{ui.esc(r["headline"])} · {r["years"]:g} yrs</span><br>'
                   f'{ui.stage_pill(r["stage"])}', unsafe_allow_html=True)
        z.markdown(ui.skill_chips(r["rows"]) + (f'<br><span class="small muted">{ui.esc(r["tips"][0])}</span>'
                                                if r["tips"] else ""), unsafe_allow_html=True)
        if w.button("Open", key=f"op{r['candidate_id']}", width="stretch"):
            ui.open_candidate(r["candidate_id"], jid)
if 2 <= len(picked) <= 3:
    if st.button(f"Compare {len(picked)}", type="primary"):
        widgets.compare(jid, picked)
elif len(picked) > 3:
    st.warning("Pick up to 3 to compare.")
