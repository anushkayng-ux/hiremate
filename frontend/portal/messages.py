"""Candidate portal: messages from the recruitment team, and replies."""
import streamlit as st

import api
import ui

ui.header("Messages", sub="Emails from the recruitment team. You can reply here.")
msgs = ui.safe(api.get, "/portal/messages") or []
if not msgs:
    ui.html_block('<div class="emptycol">No messages yet.</div>')
for m in msgs:
    mine = m["from_me"]
    with st.container(border=True):
        badge = ('<span class="pill" style="background:#2563EB;color:#fff">New</span> ' if m["unread"] else "")
        st.markdown(f'{badge}<span class="eyb">{"You replied" if mine else "From the recruitment team"} · '
                    f'{ui.esc(m["job_title"])} · {ui.fmt_ts(m["at"])}</span><br><b>{ui.esc(m["subject"])}</b>',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="small" style="white-space:pre-wrap">{ui.esc(m["body"])}</div>', unsafe_allow_html=True)
        if not mine:
            with st.expander("Reply"):
                txt = st.text_area("Your reply", key=f"t{m['id']}", placeholder="Write your message")
                if st.button("Send reply", key=f"s{m['id']}", type="primary", disabled=not txt.strip()):
                    ui.safe(api.post, f"/portal/messages/{m['id']}/reply", json={"body": txt})
                    ui.toast_next("Reply sent to the recruitment team.")
                    st.rerun()
            if m["unread"]:
                api.post(f"/portal/messages/{m['id']}/read")
