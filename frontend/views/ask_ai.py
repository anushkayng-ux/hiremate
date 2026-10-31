import streamlit as st

import chat
import ui

a, b = st.columns([5, 1], vertical_alignment="bottom")
with a:
    st.markdown('<p class="eyb">Assistant</p>', unsafe_allow_html=True)
    st.markdown("# Ask AI")
    st.markdown('<p class="muted" style="margin-top:-.6rem">Same chat as the Ask AI button. It reads every job, '
                'candidate, interview, email and document. It asks before creating, deleting or approving anything.</p>',
                unsafe_allow_html=True)
if b.button("New chat", width="stretch"):
    chat.new_chat()
    st.rerun()

clicked = chat.conversation("p")
pre = st.session_state.pop("chat_prefill", None)
inp = st.chat_input("Ask anything, or attach a JD / CVs / policy", accept_file="multiple",
                    file_type=["pdf", "docx", "txt"], key="p_input")
if pre or clicked or inp:
    if inp:
        chat.send(inp.text or "", inp.files)
    else:
        chat.send(pre or clicked)
    st.rerun()
