"""Candidate portal: my applications, progress and interview."""
import streamlit as st

import api
import ui

STEPS = ["Received", "Under review", "Shortlisted", "Interview", "Selected"]
me = st.session_state.cand
apps = ui.safe(api.get, "/portal/applications") or []
msgs = ui.safe(api.get, "/portal/messages") or []
new = sum(m["unread"] for m in msgs)
offers = ui.safe(api.get, "/portal/offers") or []

ui.header(f"Hi {me['name'].split()[0]}", sub="Here is where each of your job applications stands.")
if new:
    a, b = st.columns([4, 1.2], vertical_alignment="center")
    a.markdown(f'<div class="nextbar"><b>You have {new} new message{"s" if new > 1 else ""} from the recruitment team.</b></div>',
               unsafe_allow_html=True)
    if b.button("Read messages", type="primary", width="stretch"):
        st.switch_page("portal/messages.py")

if not apps:
    ui.html_block('<div class="emptycol">You have not applied for any job yet. Open <b>Open jobs</b> to apply.</div>')
for ap in apps:
    with st.container(border=True):
        st.markdown(f'<span class="pname" style="font-size:1.15rem">{ui.esc(ap["title"])}</span><br>'
                    f'<span class="muted small">{ui.esc(ap["location"])} · applied on {ap["applied_on"]}</span>',
                    unsafe_allow_html=True)
        if ap["stage"] == "Rejected":
            ui.html_block('<div class="flag info">This role is closed for you this time. Thank you for applying. '
                          'Your profile stays with us for future store roles.</div>')
            continue
        cur = ap["step"]
        parts = []
        for i, s in enumerate(STEPS):
            cls = "done" if i < cur or (i == cur and i == len(STEPS) - 1) else "now" if i == cur else ""
            parts.append(f'<span class="step {cls}"><span class="dot">{"✓" if cls == "done" else i + 1}</span>{s}</span>')
            if i < len(STEPS) - 1:
                parts.append(f'<span class="bar {"done" if cls == "done" else ""}"></span>')
        ui.html_block('<div class="steps">' + "".join(parts) + "</div>")
        tip = {"Applied": "We have your CV. The team will review it soon.",
               "Screening": "The team is reading your CV now.",
               "Shortlisted": "Good news: you are shortlisted. We will send an interview time soon.",
               "Interview": "Your interview is booked. Details below.",
               "Selected": "Congratulations! You have been selected. Check Messages for next steps."}.get(ap["stage"], "")
        st.markdown(f'<p class="small" style="margin:0">{tip}</p>', unsafe_allow_html=True)
        qs = ui.safe(api.get, f"/portal/applications/{ap['application_id']}/questions") or []
        if qs and any(q["answer"] in (None, "") for q in qs) and ap["stage"] in ("Applied", "Screening"):
            with st.expander("Answer a few quick questions for this job", expanded=True):
                with st.form(f"qa{ap['application_id']}"):
                    out = {}
                    for q in qs:
                        if q["kind"] == "yesno":
                            out[q["id"]] = st.radio(q["question"], ["Yes", "No"], horizontal=True, key=f"q{ap['application_id']}{q['id']}",
                                                    index=None if q["answer"] is None else ["Yes", "No"].index(q["answer"]) if q["answer"] in ("Yes", "No") else None)
                        elif q["kind"] == "number":
                            out[q["id"]] = st.text_input(q["question"], q["answer"] or "", key=f"q{ap['application_id']}{q['id']}")
                        else:
                            out[q["id"]] = st.text_input(q["question"], q["answer"] or "", key=f"q{ap['application_id']}{q['id']}")
                    if st.form_submit_button("Send answers", type="primary"):
                        ui.safe(api.post, f"/portal/applications/{ap['application_id']}/answers",
                                json={"answers": {str(k): v for k, v in out.items() if v not in (None, "")}})
                        ui.toast_next("Thanks! Your answers are with the team.")
                        st.rerun()
        for of in [o for o in offers if o["application_id"] == ap["application_id"]]:
            with st.container(border=True, key=f"offer{of['id']}"):
                st.markdown(f"**Your offer:** {of['designation']} · {of['ctc_text']} a year · joining {ui.fmt_date(of['joining_date'])}")
                with st.expander("Read the offer letter"):
                    ui.html_block(f'<div class="resume">{ui.esc(of["letter"])}</div>')
                st.download_button("Download offer letter (Word)", api.get(f"/portal/offers/{of['id']}/docx"),
                                   file_name="Offer letter.docx", key=f"odx{of['id']}", icon=":material/download:")
                if of["status"] in ("Accepted", "Declined"):
                    ui.html_block(f'<div class="{"okbox" if of["status"] == "Accepted" else "flag info"}">You '
                                  f'{of["status"].lower()} this offer.</div>')
                else:
                    note = st.text_input("Message to HR (optional)", key=f"on{of['id']}")
                    x, y = st.columns(2)
                    if x.button("Accept offer", type="primary", width="stretch", key=f"oa{of['id']}"):
                        ui.safe(api.post, f"/portal/offers/{of['id']}/respond", json={"response": "Accepted", "note": note})
                        ui.toast_next("Offer accepted. Welcome aboard!")
                        st.rerun()
                    if y.button("Decline", width="stretch", key=f"od{of['id']}"):
                        ui.safe(api.post, f"/portal/offers/{of['id']}/respond", json={"response": "Declined", "note": note})
                        ui.toast_next("Your answer is with HR.")
                        st.rerun()
        iv = ap["interview"]
        if iv:
            with st.container(border=True):
                st.markdown(f"**Interview:** {ui.fmt_date(iv['date'])}, {ui.fmt_time(iv['time'])} · {iv['mode']} · "
                            f"with {iv['interviewer']}")
                st.download_button("Add to my calendar", api.get(f"/portal/interviews/{iv['id']}/ics"),
                                   file_name="HireMate interview.ics", mime="text/calendar", key=f"ics{iv['id']}",
                                   icon=":material/calendar_add_on:")
                if iv.get("candidate_response"):
                    ui.html_block(f'<div class="okbox">You answered: {ui.esc(iv["candidate_response"])}'
                                  + (f' · "{ui.esc(iv["candidate_note"])}"' if iv.get("candidate_note") else "") + "</div>")
                else:
                    note = st.text_input("Message to the team (optional)", key=f"n{iv['id']}",
                                         placeholder="e.g. I can only come after 2 PM")
                    x, y = st.columns(2)
                    if x.button("Confirm I will come", key=f"c{iv['id']}", type="primary", width="stretch"):
                        ui.safe(api.post, f"/portal/interviews/{iv['id']}/respond", json={"response": "Confirmed", "note": note})
                        ui.toast_next("Thanks! The team can see your confirmation.")
                        st.rerun()
                    if y.button("Ask for another time", key=f"r{iv['id']}", width="stretch"):
                        ui.safe(api.post, f"/portal/interviews/{iv['id']}/respond",
                                json={"response": "Reschedule requested", "note": note})
                        ui.toast_next("Sent. The team will reply in Messages.")
                        st.rerun()
