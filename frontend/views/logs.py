"""Logs: who did what and when. Admin only."""
import streamlit as st

import api
import ui

u = st.session_state.user
ui.header("Logs", sub="Who did what and when. Only Admins can see this page.")
if u["role"] != "Admin":
    st.markdown('<div class="warnbox">Only an Admin can open the logs.</div>', unsafe_allow_html=True)
    st.stop()

PAGE = 25
ICON = {"Signed in": "🟢", "Sign-in failed": "🔴", "User added": "👤", "User updated": "👤", "Log exported": "⬇️"}
TONE = {"Sign-in failed": ("#B42318", "#FDE6E3"), "Signed in": ("#0E7A5C", "#DDF1E8")}

with st.container(border=True):
    c1, c2, c3, c4 = st.columns([2.2, 1.5, 1.5, 1.2])
    q = c1.text_input("Search", placeholder="Name, action or any word", key="lg_q")
    meta = ui.safe(api.get, "/settings/logs", limit=1) or {"actions": [], "users": []}
    action = c2.selectbox("What", ["All"] + meta["actions"], key="lg_a")
    who = c3.selectbox("Who", ["Everyone"] + meta["users"], key="lg_u")
    span = c4.selectbox("When", ["All time", "Today", "Last 7 days", "Last 30 days"], key="lg_d")
days = {"All time": 0, "Today": 1, "Last 7 days": 7, "Last 30 days": 30}[span]
flt = dict(q=q, action="" if action == "All" else action, user="" if who == "Everyone" else who, days=days)

sig = (q, action, who, span)
if st.session_state.get("lg_sig") != sig:
    st.session_state["lg_sig"], st.session_state["lg_page"] = sig, 0
pg = st.session_state.get("lg_page", 0)
d = ui.safe(api.get, "/settings/logs", limit=PAGE, offset=pg * PAGE, **flt)
if not d:
    st.stop()
total = d["total"]
pages = max(1, -(-total // PAGE))

k1, k2, k3 = st.columns(3)
with k1.container(border=True):
    ui.html_block(f'<div class="kpi">{total}</div><div class="kpil">Entries match</div>')
fails = ui.safe(api.get, "/settings/logs", limit=1, action="Sign-in failed", days=7) or {"total": 0}
with k2.container(border=True):
    ui.html_block(f'<div class="kpi">{fails["total"]}</div><div class="kpil">Failed sign-ins, last 7 days</div>')
ins = ui.safe(api.get, "/settings/logs", limit=1, action="Signed in", days=1) or {"total": 0}
with k3.container(border=True):
    ui.html_block(f'<div class="kpi">{ins["total"]}</div><div class="kpil">Sign-ins today</div>')

with st.container(border=True):
    h, b = st.columns([3, 1.2], vertical_alignment="center")
    h.markdown(f"**Activity** &nbsp;<span class='muted small'>Page {pg + 1} of {pages}</span>", unsafe_allow_html=True)
    if b.button("Prepare CSV", icon=":material/download:", width="stretch"):
        st.session_state["lg_csv"] = ui.safe(api.get, "/settings/logs/export", **flt)
    if st.session_state.get("lg_csv"):
        b.download_button(f"Download {st.session_state['lg_csv']['rows']} rows", st.session_state["lg_csv"]["csv"],
                          file_name="hiremate_logs.csv", mime="text/csv", width="stretch")
    if not d["rows"]:
        ui.html_block('<div class="emptycol">No log entries match. Clear the filters.</div>')
    for r in d["rows"]:
        fg, bg = TONE.get(r["action"], ("#3D3954", "#EEEDF3"))
        ui.html_block(
            f'<div class="prow" style="padding:.3rem 0;border-bottom:1px solid #EEF2F7">'
            f'{ui.avatar(r["by_name"] or "?", size=30)}<div style="flex:1;min-width:0">'
            f'<span class="pill" style="background:{bg};color:{fg}">{ui.esc(r["action"])}</span> '
            f'<span class="small">{ui.esc(r["detail"] or "")}</span><br>'
            f'<span class="muted small">{ui.esc(r["by_name"] or "System")} · {ui.fmt_ts(r["created_at"])}</span></div></div>')
    p1, p2, p3 = st.columns([1, 1, 4])
    if p1.button("Newer", disabled=pg == 0, icon=":material/chevron_left:", width="stretch"):
        st.session_state["lg_page"] = pg - 1
        st.rerun()
    if p2.button("Older", disabled=pg + 1 >= pages, icon=":material/chevron_right:", width="stretch"):
        st.session_state["lg_page"] = pg + 1
        st.rerun()
