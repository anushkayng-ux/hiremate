"""Candidate portal: my profile and CV."""
import streamlit as st

import api
import ui

p = ui.safe(api.get, "/portal/me")
if not p:
    st.stop()
ui.header("My profile", sub="This is what the recruitment team sees. Keep it up to date.")
left, right = st.columns([1, 1.2], gap="medium")
with left:
    with st.container(border=True):
        st.markdown(f"**{p['name']}**  \n{p['email']}")
        st.markdown(f"{p['headline'] or ''}  \n{p['years']:g} years · {p['education'] or ''}")
        with st.form("prof"):
            phone = st.text_input("Phone", p["phone"] or "")
            city = st.text_input("City", p["location"] or "")
            if st.form_submit_button("Save", type="primary"):
                ui.safe(api.patch, "/portal/me", json={"phone": phone, "location": city})
                ui.toast_next("Saved")
                st.rerun()
    with st.container(border=True):
        st.markdown("**Upload a new CV**")
        f = st.file_uploader("PDF, Word or text", type=["pdf", "docx", "txt"], label_visibility="collapsed")
        if st.button("Replace my CV", type="primary", disabled=not f):
            r = ui.safe(api.post, "/portal/me/cv", files={"file": (f.name, f.getvalue())})
            if r:
                ui.toast_next("New CV saved. Your applications use it now.")
                st.rerun()
with right:
    with st.container(border=True):
        st.markdown("**Skills we found in your CV**")
        ui.html_block("".join(f'<span class="has">{ui.esc(s)}</span>' for s in p["skills"]) or
                      '<span class="muted small">None found. Add a "Skills:" line to your CV.</span>')
        with st.expander("Your CV text"):
            st.text(p["cv_text"])

with st.expander("Delete my data"):
    st.markdown("You can ask us to delete your CV and personal details at any time (India's DPDP Act 2023). "
                "This signs you out and cannot be undone.")
    sure = st.checkbox("I understand. Delete my CV, contact details and messages.")
    if st.button("Delete my data", disabled=not sure):
        ui.safe(api.post, "/portal/me/erase")
        st.session_state.clear()
        st.rerun()
