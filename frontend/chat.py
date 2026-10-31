"""The AI chat: used by the floating Ask AI window (any page) and the full Ask AI page."""
from __future__ import annotations

import uuid

import pandas as pd
import streamlit as st

import api
import ui

STARTERS = ["List all candidates with their skills and gaps", "Who matches Store Manager?",
            "Which candidates are awaiting interviews?", "Write a JD for a cashier in Ghaziabad with 1+ years"]


def _session():
    if "chat_sid" not in st.session_state:
        st.session_state.chat_sid = f"u{st.session_state.user['id']}-{uuid.uuid4().hex[:8]}"
        st.session_state.chat_msgs = []
    return st.session_state.chat_sid, st.session_state.chat_msgs


def send(text: str, files=None) -> None:
    sid, msgs = _session()
    msgs.append({"role": "user", "text": text, "files": [f.name for f in files or []]})
    data = {"session_id": sid, "message": text}
    data |= {k: str(v) for k, v in (st.session_state.get("view_ctx") or {}).items() if v}
    with st.spinner("Thinking…"):
        try:
            r = api.post("/assistant/chat", data=data,
                         files=[("files", (f.name, f.getvalue())) for f in files] if files else None)
        except api.ApiError as e:
            r = {"reply": f"Sorry, that didn't work: {e.detail}", "suggestions": []}
    msgs.append({"role": "assistant", **r})


def new_chat() -> None:
    sid, _ = _session()
    try:
        api.delete(f"/assistant/history/{sid}")
    except api.ApiError:
        pass
    st.session_state.pop("chat_sid", None)


def _render(m: dict, last: bool, i: int, pfx: str):
    if m["role"] == "user":
        with st.chat_message("user", avatar=":material/person:"):
            if m.get("text"):
                st.markdown(m["text"])
            for f in m.get("files", []):
                ui.html_block(f'<span class="src">📎 {ui.esc(f)}</span>')
        return None
    clicked = None
    with st.chat_message("assistant", avatar=":material/auto_awesome:"):
        if m.get("badge"):
            ui.html_block(f'<span class="badge">{ui.esc(m["badge"])}</span>')
        st.markdown(m["reply"].replace("\n", "  \n") if "|" not in m["reply"] else m["reply"])
        t = m.get("table")
        if t and t.get("rows"):
            st.dataframe(pd.DataFrame(t["rows"], columns=t["head"]).astype(str), hide_index=True,
                         width="stretch")
        e = m.get("email")
        if e:
            with st.container(border=True):
                st.markdown(f"**{e['subject']}**  \nTo: {e.get('to_email') or e['candidate']}")
                st.text(e["body"])
        d = m.get("doc")
        if d:
            with st.container(border=True):
                st.markdown(f"📄 **{d['title']}** · {d['file_name']}")
                with st.expander("Preview"):
                    st.text(d["text"])
                try:
                    st.download_button("Download .docx", api.get(f"/knowledge/files/{d['file_id']}"),
                                       file_name=d["file_name"], key=f"{pfx}dl{i}",
                                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                except api.ApiError:
                    st.caption("File no longer available.")
        if m.get("sources"):
            ui.html_block("".join(f'<span class="src">[{s["n"]}] {ui.esc(s["title"])}</span>' for s in m["sources"]))
        ln = m.get("link")
        if ln and st.button(ln["label"] + " →", key=f"{pfx}ln{i}"):
            if ln["page"] == "job":
                ui.open_job(ln["job_id"])
            elif ln["page"] == "candidate":
                ui.open_candidate(ln["candidate_id"], ln.get("job_id"))
            else:
                ui.go(ln["page"])
        if last and m.get("suggestions"):
            for j, s in enumerate(m["suggestions"]):
                if st.button(s, key=f"{pfx}sg{i}-{j}"):
                    clicked = s
    return clicked


def conversation(pfx: str) -> str | None:
    """Draw all messages. Returns a suggestion the user clicked, if any."""
    _, msgs = _session()
    clicked = None
    if not msgs:
        with st.chat_message("assistant", avatar=":material/auto_awesome:"):
            st.markdown(f"Hi {st.session_state.user['name'].split()[0]}. Ask me anything about your jobs, candidates, "
                        "interviews or policies, from any page. You can also attach a JD or CVs.")
            for j, s in enumerate(STARTERS):
                if st.button(s, key=f"{pfx}st{j}"):
                    clicked = s
    for i, m in enumerate(msgs):
        c = _render(m, i == len(msgs) - 1, i, pfx)
        clicked = clicked or c
    return clicked


@st.dialog("Ask AI", width="large")
def window():
    top = st.columns([4, 1])
    ctx = st.session_state.get("view_ctx") or {}
    top[0].caption("I can see everything in HireMate, whatever page you're on."
                   + (" I'll use the page you have open for 'this job' / 'this candidate'." if ctx else ""))
    if top[1].button("New chat", key="w_new", width="stretch"):
        new_chat()
    box = st.container(height=470)
    with box:
        clicked = conversation("w")
    pre = st.session_state.pop("chat_prefill", None)
    inp = st.chat_input("Ask anything, or attach a JD / CVs / policy", accept_file="multiple",
                        file_type=["pdf", "docx", "txt"], key="w_input")
    if pre or clicked or inp:
        if inp:
            send(inp.text or "", inp.files)
        else:
            send(pre or clicked)
        st.rerun(scope="fragment")


def open_window(prefill: str | None = None) -> None:
    if prefill:
        st.session_state.chat_prefill = prefill
    window()
