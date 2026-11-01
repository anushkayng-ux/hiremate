"""Candidate portal (Plus): my next steps – timing, pick an interview slot, quick screening, billing test, joining documents."""
import time

import streamlit as st

import api
import ui

me = st.session_state.cand
apps = ui.safe(api.get, "/portal/applications") or []
timing = {t["application_id"]: t for t in (ui.safe(api.get, "/portal/plus/timing") or [])}

ui.header("My next steps", sub="Everything you can do now to move your application forward.")
if not apps:
    ui.html_block('<div class="emptycol">Apply for a job first (Open jobs).</div>')

for ap in apps:
    aid = ap["application_id"]
    if ap["stage"] == "Rejected":
        continue
    with st.container(border=True):
        st.markdown(f'<span class="pname" style="font-size:1.1rem">{ui.esc(ap["title"])}</span> &nbsp;'
                    f'<span class="pill" style="background:#E7E3F6;color:#2B2350">{ui.esc(ap["label"])}</span>',
                    unsafe_allow_html=True)
        t = timing.get(aid)
        if t:
            ui.html_block(f'<div class="{"flag" if t["late"] else "note"}">⏱ {ui.esc(t["text"])}</div>')

        # ---------------- pick your own interview slot
        if ap["stage"] == "Shortlisted":
            st.markdown("**Pick your interview time**")
            slots = ui.safe(api.get, f"/portal/plus/slots/{aid}") or []
            mode = st.radio("How", ["In person", "Video call", "Phone"], horizontal=True, key=f"m{aid}")
            cols = st.columns(3)
            for i, s in enumerate(slots):
                if cols[i % 3].button(s["label"], key=f"sl{aid}{i}", width="stretch"):
                    if ui.safe(api.post, f"/portal/plus/slots/{aid}", json={"date": s["date"], "time": s["time"], "mode": mode}):
                        ui.toast_next(f"Booked {s['label']}. See it in My applications.")
                        st.rerun()

        # ---------------- AI chat screening
        if ap["stage"] in ("Applied", "Screening", "Shortlisted"):
            sc = ui.safe(api.get, f"/portal/plus/screen/{aid}") or {"done": True}
            if sc["done"]:
                ui.html_block('<div class="okbox">✓ Quick screening answered. Thank you!</div>')
            else:
                with st.expander("Answer 5 quick questions (about 5 minutes). It helps the team know you better.", expanded=False):
                    msgs = st.session_state.setdefault(f"chat{aid}", [])
                    qs = sc["questions"]
                    for i, m in enumerate(msgs):
                        with st.chat_message("assistant"):
                            st.write(qs[i]["q"])
                        with st.chat_message("user"):
                            st.write(m)
                    if len(msgs) < len(qs):
                        with st.chat_message("assistant"):
                            st.write(f"({len(msgs) + 1}/{len(qs)}) {qs[len(msgs)]['q']}")
                        ans = st.chat_input("Type your answer…", key=f"ci{aid}")
                        if ans:
                            msgs.append(ans)
                            st.rerun()
                    else:
                        st.success("All done. Send your answers?")
                        if st.button("Send answers", type="primary", key=f"ss{aid}"):
                            ui.safe(api.post, f"/portal/plus/screen/{aid}", json={"answers": msgs})
                            st.session_state.pop(f"chat{aid}", None)
                            ui.toast_next("Thanks! Your answers are with the team.")
                            st.rerun()

        # ---------------- billing test (cashier jobs)
        ti = ui.safe(api.get, f"/portal/plus/test/{aid}") or {}
        if ti.get("applies") and ap["stage"] in ("Applied", "Screening", "Shortlisted", "Interview"):
            if ti.get("done"):
                ui.html_block('<div class="okbox">✓ Billing test done. The team will see your result.</div>')
            else:
                key = f"test{aid}"
                if key not in st.session_state:
                    st.markdown("**Billing test** · 8 quick sums (bill totals, change, discounts). About 8 minutes. "
                                "Use paper if you like; no calculator.")
                    if st.button("Start the test", key=f"st{aid}", type="primary"):
                        st.session_state[key] = {**api.post(f"/portal/plus/test/{aid}/start"), "t0": time.time()}
                        st.rerun()
                else:
                    tst = st.session_state[key]
                    left = max(0, tst["minutes"] * 60 - int(time.time() - tst["t0"]))
                    st.caption(f"Time left: about {left // 60} min (the clock started when you pressed Start).")
                    with st.form(f"tf{aid}"):
                        ans = [st.text_input(f"{q['n'] + 1}. {q['q']}", key=f"ta{aid}{q['n']}", placeholder="₹") for q in tst["questions"]]
                        if st.form_submit_button("Submit test", type="primary"):
                            ui.safe(api.post, f"/portal/plus/test/submit/{tst['test_id']}", json={"answers": ans})
                            st.session_state.pop(key, None)
                            ui.toast_next("Test submitted. Thank you!")
                            st.rerun()

        # ---------------- joining documents
        jn = ui.safe(api.get, f"/portal/plus/joining/{aid}") or {}
        if jn.get("open"):
            st.markdown(f"**Joining documents** · {jn['done']} of {jn['total']} checked by HR")
            for it in jn["items"]:
                a, b = st.columns([3, 2], vertical_alignment="center")
                state = "✅ Checked" if it["verified"] else "📄 Uploaded, waiting for HR" if it["uploaded"] else "⬜ Not yet"
                a.markdown(f"{it['doc']}<br><span class='small muted'>{state}</span>", unsafe_allow_html=True)
                if not it["verified"]:
                    f = b.file_uploader("Upload", type=["pdf", "jpg", "jpeg", "png"], key=f"up{aid}{it['doc']}",
                                        label_visibility="collapsed")
                    if f and b.button("Send", key=f"us{aid}{it['doc']}", width="stretch"):
                        ui.safe(api.post, f"/portal/plus/joining/{aid}", data={"doc": it["doc"]},
                                files={"file": (f.name, f.getvalue())})
                        ui.toast_next(f"{it['doc']} uploaded")
                        st.rerun()
