import streamlit as st

import api
import ui

ui.header("Documents & policies", "",
          "JDs, CVs, policies and FAQs. The AI answers questions only from what's here.")
rec = st.session_state.user["role"] in ("Admin", "Recruiter")


@st.dialog("Upload documents", width="large")
def upload():
    st.caption("Drop any mix of JDs, CVs and policies. I sort each one: JDs become jobs, CVs become candidates, "
               "the rest become policy documents.")
    fs = st.file_uploader("Files", type=["pdf", "docx", "txt"], accept_multiple_files=True)
    if st.button("Upload", type="primary", disabled=not fs):
        res = ui.safe(api.post, "/knowledge/upload", files=[("files", (f.name, f.getvalue())) for f in fs]) or []
        for r in res:
            (st.success if r["ok"] else st.error)(f"{r['file_name']}: " + (f"added as {r['kind']} — {r['title']}"
                                                                          if r["ok"] else r["error"]))
        st.session_state.kb_dirty = True


@st.dialog("New document", width="large")
def create():
    t = st.text_input("Title")
    k = st.selectbox("Type", ["Policy", "FAQ", "Other"])
    x = st.text_area("Text", height=240)
    if st.button("Save", type="primary", disabled=not (t and x)):
        api.post("/knowledge", json={"title": t, "text": x, "type": k})
        ui.toast_next(f"Added {t}")
        st.rerun()


a, b, c, d = st.columns([2.6, 1.2, 1, 1], vertical_alignment="bottom")
q = a.text_input("Search", placeholder="Search titles and text", label_visibility="collapsed")
kind = b.selectbox("Type", ["All", "Policy", "FAQ", "JD", "CV", "Other"], label_visibility="collapsed")
if c.button("Upload", width="stretch", disabled=not rec):
    upload()
if d.button("New", icon=":material/add:", type="primary", width="stretch", disabled=not rec):
    create()
if st.session_state.pop("kb_dirty", False):
    st.rerun()

with st.container(border=True):
    ask = st.text_input("Ask the knowledge store", placeholder="e.g. Can a candidate reschedule twice?")
    if ask:
        r = api.post("/knowledge/ask", json={"question": ask})
        st.markdown(r["text"])
        if r["sources"]:
            ui.html_block("".join(f'<span class="src">[{s["n"]}] {ui.esc(s["title"])} · {s["type"]}</span>'
                                  for s in r["sources"]))

docs = ui.safe(api.get, "/knowledge", kind=None if kind == "All" else kind, q=q) or []
st.caption(f"{len(docs)} documents")
for doc in docs:
    with st.expander(f"{doc['title']}  ·  {doc['kind']}" + (f"  ·  {doc['subtitle']}" if doc["subtitle"] else "")):
        st.caption(f"Source: {doc['source'] or '—'}" + (f" · file {doc['file_name']}" if doc["file_name"] else "")
                   + f" · added {ui.fmt_ts(doc['created_at'])}")
        is_doc = doc["key"].startswith("doc:")
        if is_doc and rec:
            nt = st.text_area("Text", doc["text"], height=160, key=f"t{doc['key']}")
            x, y, z, w = st.columns(4)
            if x.button("Save", key=f"s{doc['key']}", width="stretch") and nt != doc["text"]:
                api.patch(f"/knowledge/{doc['id']}", json={"text": nt})
                ui.toast_next("Saved")
                st.rerun()
            f = api.post("/knowledge/docx", json={"title": doc["title"], "text": nt}) if y.button(
                "Make .docx", key=f"m{doc['key']}", width="stretch") else None
            if f:
                st.session_state[f"f{doc['key']}"] = f
            if st.session_state.get(f"f{doc['key']}"):
                ff = st.session_state[f"f{doc['key']}"]
                z.download_button("Download", api.get(f"/knowledge/files/{ff['id']}"), file_name=ff["name"],
                                  key=f"d{doc['key']}", width="stretch")
            if w.button("Delete", key=f"x{doc['key']}", width="stretch"):
                st.session_state[f"cx{doc['key']}"] = True
            if st.session_state.get(f"cx{doc['key']}"):
                st.warning("Delete this document? The AI won't use it after this.")
                if st.button("Yes, delete", key=f"y{doc['key']}", type="primary"):
                    api.delete(f"/knowledge/{doc['id']}")
                    ui.toast_next(f"Deleted {doc['title']}")
                    st.rerun()
        else:
            st.text(doc["text"])
            if st.button("Open " + ("job" if doc["kind"] == "JD" else "profile" if doc["kind"] == "CV" else ""),
                         key=f"o{doc['key']}"):
                if doc["kind"] == "JD":
                    ui.open_job(doc["id"])
                elif doc["kind"] == "CV":
                    ui.open_candidate(doc["id"])
