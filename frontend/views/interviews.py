import streamlit as st

import api
import ui

ui.header("Interviews", sub="Booked interviews. Open one to add feedback.")
tab1, tab2 = st.tabs(["Upcoming", "Past"])
for tab, when in ((tab1, "upcoming"), (tab2, "past")):
    with tab:
        ivs = ui.safe(api.get, "/interviews", when=when) or []
        if not ivs:
            st.markdown('<p class="muted">Nothing here.</p>', unsafe_allow_html=True)
        for iv in ivs:
            with st.container(border=True):
                x, y, z, w = st.columns([2.4, 2.6, 1.3, 1], vertical_alignment="center")
                x.markdown(f'<b>{ui.esc(ui.name(iv["candidate"], iv["candidate_id"]))}</b><br>'
                           f'<span class="muted small">{ui.esc(iv["job_title"])}</span>', unsafe_allow_html=True)
                y.markdown(f'{ui.fmt_date(iv["date"])}, {ui.fmt_time(iv["time"])}<br><span class="muted small">'
                           f'{ui.esc(iv["mode"])} · {ui.esc(iv["interviewer"])}</span>', unsafe_allow_html=True)
                label = "Feedback in" if iv["has_feedback"] else iv["status"] if iv["status"] != "Scheduled" or when == "upcoming" else "Feedback due"
                z.markdown(f'<span class="pill" style="background:{"#DDF1E8" if iv["has_feedback"] else "#FEF3C7"}">{label}</span>',
                           unsafe_allow_html=True)
                if w.button("View", key=f"iv{iv['id']}", width="stretch"):
                    ui.open_candidate(iv["candidate_id"], iv["job_id"])
st.caption("To book a new interview, open the candidate's profile → Interview, or ask AI: "
           "\"Schedule an interview for Kavya on Tuesday at 3pm\".")
