import streamlit as st
import requests

API_URL = "http://localhost:8000"

st.set_page_config(page_title="FSANZ Regulatory Assistant", layout="wide")
st.title("FSANZ Regulatory Affairs Assistant")
st.caption("Based on FSANZ Food Standards Code, March 2025")

with st.sidebar:
    st.header("Try These Questions")
    examples = [
        "Is potassium sorbate allowed in fruit juice?",
        "What allergens must be declared on labels?",
        "What are the NIP requirements for beverages?",
        "What is the maximum sulfur dioxide level in wine?",
        "What warning statements are required for high caffeine drinks?"
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state["prefill"] = ex

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prefill = st.session_state.pop("prefill", "")
user_input = st.chat_input("Ask a regulatory question...") or prefill

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Searching FSANZ Code..."):
            try:
                res = requests.post(
                    f"{API_URL}/ask",
                    json={"question": user_input},
                    timeout=30
                )
                data = res.json()
                st.markdown(data["answer"])
                st.caption(f"Source: {data['source']} | Pages: {data['pages_referenced']}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": data["answer"]
                })
            except Exception as e:
                st.error(f"Backend error: {e}")
