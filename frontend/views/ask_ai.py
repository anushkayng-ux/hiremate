"""Ask AI: full page chat. Scrolls like a normal page; the box stays at the bottom."""
import streamlit as st

import chat
import ui

ctx = st.session_state.get("chat_ctx") or {}
back = st.session_state.get("chat_back", "dashboard")

top, a, b = st.columns([4, 1.2, 1.2], vertical_alignment="center")
with top:
    st.markdown('<p class="eyb">Assistant</p>', unsafe_allow_html=True)
    st.markdown("## Ask AI")
if a.button("Back", icon=":material/arrow_back:", width="stretch"):
    ui.go(back if back in ui.PAGES and back != "asha" else "dashboard")
if b.button("New chat", icon=":material/add:", width="stretch"):
    chat.new_chat()
    st.session_state.pop("chat_ctx", None)
    st.rerun()
st.markdown('<p class="muted" style="margin-top:-.4rem">I read every job, candidate, interview, email and policy. '
            'I ask before creating, deleting or sending anything.'
            + (" I will use the job or candidate you had open for 'this job' and 'this candidate'." if ctx else "")
            + '</p>', unsafe_allow_html=True)

clicked = chat.conversation("p")
pre = st.session_state.pop("chat_prefill", None)
inp = st.chat_input("Ask anything, or attach a JD / CVs / policy", accept_file="multiple",
                    file_type=["pdf", "docx", "txt"], key="p_input")
if pre or clicked or inp:
    if inp:
        chat.send(inp.text or "", inp.files)
    else:
        chat.send(pre or clicked)
    st.session_state["_scroll_chat"] = True
    st.rerun()
if st.session_state.pop("_scroll_chat", False) or len(st.session_state.get("chat_msgs", [])) > 2:
    chat.scroll_to_end()
