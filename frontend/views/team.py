"""Team: who can sign in, and what each role can do. Admin adds people, changes roles, switches accounts off."""
import streamlit as st

import api
import ui

me = st.session_state.user
is_admin = me["role"] == "Admin"

if st.button("← Settings", type="tertiary"):
    ui.go("settings")
ui.header("Team", sub="Who can sign in to HireMate, and what each role can do.")

ROLES = {"Admin": ("#1D4ED8", "Everything a Recruiter can do, plus: add or edit team members, change settings and AI, reset demo data."),
         "Recruiter": ("#15803D", "Jobs, CVs, matching, shortlist, book interviews, drafts and sends emails, Ask AI, reports."),
         "Interviewer": ("#B45309", "Sees only the interviews and candidates given to them. Adds their own feedback and scores.")}
with st.container(border=True):
    st.markdown("**Roles**")
    for r, (col, text) in ROLES.items():
        ui.html_block(f'<div class="prow" style="align-items:flex-start;margin:.35rem 0"><span class="pill" '
                      f'style="background:{col};color:#fff;min-width:92px;text-align:center">{r}</span>'
                      f'<span class="small">{text}</span></div>')

users = ui.safe(api.get, "/settings/users") or []
active = [x for x in users if x.get("active", 1)]
with st.container(border=True):
    st.markdown(f"**People** &nbsp;<span class='pill' style='background:#2563EB;color:#fff'>{len(active)} active</span>",
                unsafe_allow_html=True)
    for x in users:
        on = bool(x.get("active", 1))
        a, b = st.columns([4, 1.3], vertical_alignment="center", gap="small")
        last = (x.get("last_login") or "")[:16].replace("T", " ") or "never"
        a.markdown(f'<div class="prow">{ui.avatar(x["name"], size=38)}<div><b>{ui.esc(x["name"])}</b>'
                   f'{" (you)" if x["id"] == me["id"] else ""}<br><span class="muted small">{ui.esc(x["email"])} · '
                   f'{x["role"]} · {"Active" if on else "Turned off"} · last sign-in {last}</span></div></div>',
                   unsafe_allow_html=True)
        if is_admin and b.button("Edit", key=f"ue{x['id']}", width="stretch"):
            st.session_state["edit_user"] = x["id"] if st.session_state.get("edit_user") != x["id"] else None
        if is_admin and st.session_state.get("edit_user") == x["id"]:
            with st.form(f"uf{x['id']}", border=True):
                n = st.text_input("Name", value=x["name"])
                r = st.selectbox("Role", list(ROLES), index=list(ROLES).index(x["role"]))
                act = st.checkbox("Account is on (can sign in)", value=on, disabled=x["id"] == me["id"])
                pw = st.text_input("New password (leave empty to keep the old one)", type="password")
                if st.form_submit_button("Save", type="primary"):
                    body = {"name": n, "role": r, "active": act}
                    if pw:
                        body["password"] = pw
                    if ui.safe(api.patch, f"/settings/users/{x['id']}", json=body):
                        st.session_state.pop("edit_user", None)
                        ui.toast_next(f"Saved {n}")
                        st.rerun()

if is_admin:
    with st.container(border=True):
        st.markdown("**Add a team member**")
        with st.form("nu", clear_on_submit=True):
            c1, c2 = st.columns(2)
            n = c1.text_input("Name")
            e = c2.text_input("Work email")
            c3, c4 = st.columns(2)
            r = c3.selectbox("Role", list(ROLES), index=1)
            p = c4.text_input("Temporary password (6+ characters)", type="password")
            if st.form_submit_button("Add person", type="primary"):
                if not (n and e and p):
                    st.error("Fill in name, email and a temporary password.")
                elif ui.safe(api.post, "/settings/users", json={"name": n, "email": e, "role": r, "password": p}):
                    ui.toast_next(f"Added {n} as {r}")
                    st.rerun()
        st.caption("Nobody is ever deleted. Turn an account off to stop sign-in. There is always at least one active Admin.")
else:
    st.info("Only an Admin can add or change team members.")
