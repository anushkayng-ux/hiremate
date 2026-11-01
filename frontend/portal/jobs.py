"""Candidate portal: open jobs and apply."""
import streamlit as st

import api
import ui

ui.header("Open jobs", sub="Apply with one click. We use the CV in your profile.")
jobs = ui.safe(api.get, "/portal/jobs") or []
if not jobs:
    ui.html_block('<div class="emptycol">No open jobs right now.</div>')
for j in jobs:
    with st.container(border=True):
        x, y = st.columns([4, 1.2], vertical_alignment="center")
        x.markdown(f'<span class="pname">{ui.esc(j["title"])}</span><br><span class="muted small">{ui.esc(j["location"])} · '
                   f'{j["min_years"]:g}+ years</span><br><span class="small">Skills needed: {ui.esc(", ".join(j["must"]))}</span>',
                   unsafe_allow_html=True)
        if j["applied"]:
            y.markdown('<span class="pill" style="background:#DDF1E8;color:#0E7A5C">Applied ✓</span>', unsafe_allow_html=True)
        elif y.button("Apply", key=f"a{j['id']}", type="primary", width="stretch"):
            r = ui.safe(api.post, "/portal/apply", json={"job_id": j["id"]})
            if r:
                ui.toast_next(f"Applied for {r['title']}. Track it in My applications.")
                st.rerun()
        with st.expander("Read the job description"):
            st.text(j["description"])
