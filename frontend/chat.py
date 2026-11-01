"""The AI chat: used by the floating Ask AI window (any page) and the full Ask AI page."""
from __future__ import annotations

import uuid

import pandas as pd
import streamlit as st

import api
import ui

STARTERS = ["What should I do today?", "Who should I hire first and why?", "Who is waiting too long?",
            "List all candidates with their skills and gaps", "Write a JD for a cashier in Ghaziabad with 1+ years"]


def _session():
    if "chat_sid" not in st.session_state:
        st.session_state.chat_sid = f"u{st.session_state.user['id']}-{uuid.uuid4().hex[:8]}"
        st.session_state.chat_msgs = []
    return st.session_state.chat_sid, st.session_state.chat_msgs


def send(text: str, files=None) -> None:
    sid, msgs = _session()
    msgs.append({"role": "user", "text": text, "files": [f.name for f in files or []]})
    data = {"session_id": sid, "message": text}
    ctx = st.session_state.get("view_ctx") or st.session_state.get("chat_ctx") or {}
    data |= {k: str(v) for k, v in ctx.items() if v}
    files_arg = [("files", (f.name, f.getvalue())) for f in files] if files else None
    holder: dict = {}

    def pieces():
        """Words as they arrive (for st.write_stream); keeps the final reply in `holder`."""
        try:
            for kind, val in api.stream_chat(data, files_arg):
                if kind == "delta":
                    yield val
                else:
                    holder["r"] = val
        except api.ApiError as e:
            holder["r"] = {"reply": f"Sorry, that didn't work: {e.detail}", "suggestions": []}

    with st.chat_message("assistant", avatar=":material/auto_awesome:"):
        wait = st.empty()
        wait.caption("Thinking…")

        def clear_first(gen):
            for p in gen:
                wait.empty()
                yield p
        streamed = st.write_stream(clear_first(pieces()))
        wait.empty()
    r = holder.get("r") or {"reply": streamed or "Sorry, no answer came back. Please try again.", "suggestions": []}
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
        if m.get("bullets"):
            st.markdown("\n".join(f"- {b}" for b in m["bullets"]))
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


def open_window(prefill: str | None = None) -> None:
    """Open the full Ask AI page. Remembers the page and the job / candidate you were looking at."""
    if prefill:
        st.session_state.chat_prefill = prefill
    ctx = st.session_state.get("view_ctx")
    if ctx:
        st.session_state.chat_ctx = dict(ctx)
    if "chat_back" not in st.session_state or st.session_state.get("_nav_key") not in (None, "asha"):
        st.session_state.chat_back = st.session_state.get("_nav_key") or "dashboard"
    ui.go("asha")


def scroll_to_end() -> None:
    """Scroll the page down to the newest message."""
    import streamlit.components.v1 as components
    components.html(
        "<script>setTimeout(()=>{const d=window.parent.document;"
        "const m=d.querySelector('[data-testid=\"stAppScrollToBottomContainer\"]')||d.querySelector('[data-testid=\"stMain\"]')||d.querySelector('section.main')||d.querySelector('main');"
        "if(m){m.scrollTo({top:m.scrollHeight,behavior:'smooth'});}},250);</script>", height=0)
