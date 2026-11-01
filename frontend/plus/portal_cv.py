"""Candidate portal (Plus): improve my CV – CV coach for a job, and 'No CV? Answer 6 questions'."""
import streamlit as st

import api
import ui
from plus import plus_ui as pu  # noqa: F401  (shared styles)

ui.header("Improve my CV", sub="Simple tips so the team sees your real experience. We never show scores.")
jobs = ui.safe(api.get, "/portal/jobs") or []
tab1, tab2 = st.tabs(["CV coach", "Make a new CV from 6 questions"])

with tab1:
    if not jobs:
        st.info("No open jobs right now.")
    else:
        jm = {j["id"]: j["title"] for j in jobs}
        jid = st.selectbox("Which job do you want?", list(jm), format_func=jm.get)
        co = ui.safe(api.get, f"/portal/plus/coach/{jid}")
        if co:
            if co["strengths"]:
                ui.html_block("<b>Your CV already shows:</b> " + "".join(f'<span class="has">✓ {ui.esc(s)}</span>' for s in co["strengths"]))
            if co["done"]:
                ui.html_block('<div class="okbox" style="margin-top:.5rem">Your CV covers everything this job asks for. 👍</div>')
            for t in co["tips"]:
                with st.container(border=True):
                    st.markdown(f"**{t['title']}**")
                    st.caption(t["detail"])
                    ui.html_block(f'<div class="ev">Example: "{ui.esc(t["example"])}"</div>')
            if co["tips"]:
                st.caption("Only add what is true. Then upload your new CV in My profile, or make one in the next tab.")

with tab2:
    st.markdown("No CV, or an old one? Answer these and we'll write a clean CV for you. Hindi or English is fine.")
    qs = ui.safe(api.get, "/portal/plus/cv-questions") or []
    me = st.session_state.cand
    with st.form("buildcv"):
        ans = {}
        for q in qs:
            dflt = me["name"] if q["key"] == "name" else (me.get("phone") or "") if q["key"] == "phone" else ""
            if q["key"] in ("jobs", "daily", "proud"):
                ans[q["key"]] = st.text_area(q["q"], dflt, placeholder=q["hint"], height=80)
            else:
                ans[q["key"]] = st.text_input(q["q"], dflt, placeholder=q["hint"])
        if st.form_submit_button("Write my CV", type="primary"):
            st.session_state["built_cv"] = ui.safe(api.post, "/portal/plus/build-cv", json={"answers": ans})
    b = st.session_state.get("built_cv")
    if b:
        txt = st.text_area("Your new CV (you can edit it)", b["text"], height=320)
        a, c = st.columns(2)
        a.download_button("Download as text", txt, file_name="My CV.txt", width="stretch")
        if c.button("Use this as my CV", type="primary", width="stretch"):
            if ui.safe(api.post, "/portal/me/cv", data={"text": txt}):
                st.session_state.pop("built_cv", None)
                ui.toast_next("Saved. Your applications now use this CV.")
                st.rerun()
