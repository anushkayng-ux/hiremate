import uuid

import streamlit as st

import api
import ui


def preview_box(p: dict) -> None:
    ui.html_block(f'<p class="eyb">What I found</p><b>{ui.esc(p["title"])}</b> · {ui.esc(p["location"])} · '
                  f'{p["min_years"]:g}+ years<br>'
                  f'<span class="small">Must have: {ui.esc(", ".join(p["must"]) or "none")}<br>'
                  f'Nice to have: {ui.esc(", ".join(p["nice"]) or "none")}</span>')
    for f in p.get("check", []):
        (st.success if f["level"] == "good" else st.warning if f["level"] == "warn" else st.error)(
            f"{f['title']} — {f['fix']}")


@st.dialog("Create a job", width="large")
def create_dialog():
    tab1, tab2, tab3 = st.tabs(["Upload JD", "Paste text", "Write with AI"])
    with tab1:
        f = st.file_uploader("PDF, Word or text", type=["pdf", "docx", "txt"], key="jdfile")
        if f:
            p = ui.safe(api.post, "/jobs/preview", files={"file": (f.name, f.getvalue())})
            if p:
                preview_box(p)
                if st.button("Create job", type="primary", key="c1"):
                    j = ui.safe(api.post, "/jobs/upload", files={"file": (f.name, f.getvalue())})
                    if j:
                        ui.toast_next(f"Created {j['title']}")
                        ui.open_job(j["id"])
    with tab2:
        txt = st.text_area("Job description", height=220, key="jdtext",
                           placeholder="Title on the first line, then Location:, Must have:, Nice to have:, Experience: …")
        if txt and len(txt) > 20:
            p = ui.safe(api.post, "/jobs/preview", data={"text": txt})
            if p:
                preview_box(p)
                if st.button("Create job", type="primary", key="c2"):
                    j = ui.safe(api.post, "/jobs", json={"text": txt})
                    if j:
                        ui.toast_next(f"Created {j['title']}")
                        ui.open_job(j["id"])
    with tab3:
        desc = st.text_input("Describe the role", placeholder="A visual merchandiser in Noida with 2+ years")
        if st.button("Write the JD", disabled=not desc):
            r = ui.safe(api.post, "/assistant/chat",
                        data={"session_id": "jd-" + uuid.uuid4().hex, "message": f"Write a JD for {desc}"})
            if r and r.get("doc"):
                st.session_state.jd_draft = r["doc"]["text"]
        if st.session_state.get("jd_draft"):
            draft = st.text_area("Draft (edit freely)", st.session_state.jd_draft, height=260, key="jddraft")
            if st.button("Create job", type="primary", key="c3"):
                j = ui.safe(api.post, "/jobs", json={"text": draft})
                if j:
                    st.session_state.pop("jd_draft", None)
                    ui.toast_next(f"Created {j['title']}")
                    ui.open_job(j["id"])


h1, h2 = st.columns([4, 1.2], vertical_alignment="center")
with h1:
    ui.header("Jobs", sub="Open a job to see its candidates, best match first.")
rec = st.session_state.user["role"] in ("Admin", "Recruiter")
if h2.button("New job", icon=":material/add:", type="primary", width="stretch", disabled=not rec) \
        or st.session_state.pop("open_create", False):
    create_dialog()

a, b = st.columns([3, 1.2], vertical_alignment="bottom")
q = a.text_input("Search", placeholder="Search by job title or city", label_visibility="collapsed")
status = b.segmented_control("Show", ["Open", "Paused", "Closed", "All"], default="Open", label_visibility="collapsed") or "Open"

jobs = ui.safe(api.get, "/jobs", q=q, status=None if status == "All" else status) or []
if not jobs:
    ui.html_block('<div class="emptycol">No jobs here yet. Click <b>New job</b> to add one from a JD.</div>')
for j in jobs:
    with st.container(border=True):
        x, y, z = st.columns([3, 3.4, 1], vertical_alignment="center")
        x.markdown(f'<span class="pname">{ui.esc(j["title"])}</span><br><span class="muted small">{ui.esc(j["location"])} · '
                   f'{j["min_years"]:g}+ years · {j["status"]}</span>', unsafe_allow_html=True)
        sc = j["stage_counts"]
        y.markdown(" ".join(f'<span class="pill" style="background:#EEEDF3;color:#3D3954">{ui.LABEL[s]} '
                            f'<b>{sc.get(s, 0)}</b></span>' for s in ui.FLOW), unsafe_allow_html=True)
        if z.button("Open", key=f"j{j['id']}", type="primary", width="stretch"):
            ui.open_job(j["id"])
