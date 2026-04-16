import streamlit as st
import requests

API_URL = "http://localhost:8000"

st.set_page_config(
    page_title="FSANZ Regulatory Assistant",
    layout="wide"
)

st.title("FSANZ Regulatory Affairs Assistant")
st.caption("Powered by FSANZ Food Standards Code, March 2025")

# --- Sidebar ---
with st.sidebar:
    st.header("Chat — Try These Questions")
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

    st.divider()
    st.header("Compliance — Try This Example")
    sample = "Filtered water, apple juice (30%), raspberry juice (8%), blueberry juice (5%), sugar (45g/kg), natural flavour, potassium sorbate (200mg/kg)"
    if st.button("Load sample ingredient list", use_container_width=True):
        st.session_state["compliance_input"] = sample

    st.divider()
    st.markdown("**How it works**")
    st.markdown("""
- **Chat Tab** → Ask any FSANZ regulatory question
- **Compliance Tab** → Paste your ingredient list and get an instant compliance report
- All queries are logged to AWS S3
""")

# --- Two Tabs ---
tab1, tab2 = st.tabs(["Chat Assistant", "Compliance Checker"])


# =====================
# TAB 1 — CHAT
# =====================
with tab1:
    st.subheader("Ask a Regulatory Question")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prefill    = st.session_state.pop("prefill", "")
    user_input = st.chat_input("Ask a regulatory question...") or prefill

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Searching FSANZ Code..."):
                try:
                    res  = requests.post(
                        f"{API_URL}/ask",
                        json={"question": user_input},
                        timeout=30
                    )
                    data = res.json()
                    st.markdown(data["answer"])
                    st.caption(f"Source: {data['source']} | Pages: {data['pages_referenced']}")
                    st.session_state.messages.append({
                        "role":    "assistant",
                        "content": data["answer"]
                    })
                except Exception as e:
                    st.error(f"Backend error: {e}")


# =====================
# TAB 2 — COMPLIANCE
# =====================
with tab2:
    st.subheader("AI Compliance Checker")
    st.markdown("Paste your product ingredient list below. The system will automatically check each ingredient against the FSANZ Food Standards Code and flag any compliance issues.")

    default_input = st.session_state.pop("compliance_input", "")

    ingredient_input = st.text_area(
        "Paste your ingredient list here",
        value=default_input,
        placeholder="e.g. Filtered water, apple juice (30%), sugar (45g/kg), natural flavour, potassium sorbate (200mg/kg)",
        height=120
    )

    if st.button("Check Compliance", type="primary", use_container_width=True):
        if not ingredient_input.strip():
            st.warning("Please enter an ingredient list first.")
        else:
            with st.spinner("Checking each ingredient against FSANZ Code... This may take 30-60 seconds."):
                try:
                    res  = requests.post(
                        f"{API_URL}/check-compliance",
                        json={"ingredient_text": ingredient_input},
                        timeout=120
                    )
                    data = res.json()

                    st.divider()

                    # Overall status banner
                    if data["overall_status"] == "PASS":
                        st.success(f"OVERALL STATUS: COMPLIANT — {data['summary']}")
                    elif data["overall_status"] == "WARNING":
                        st.warning(f"OVERALL STATUS: REVIEW REQUIRED — {data['summary']}")
                    elif data["overall_status"] == "FAIL":
                        st.error(f"OVERALL STATUS: NON-COMPLIANT — {data['summary']}")
                    else:
                        st.error(f"ERROR — {data['summary']}")

                    # Summary metrics
                    st.divider()
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Total Checked", data["total_checks"])
                    col2.metric("Passed",        data["passed"],   delta=None)
                    col3.metric("Warnings",      data["warnings"], delta=None)
                    col4.metric("Failed",        data["failed"],   delta=None)

                    # Individual results
                    st.divider()
                    st.subheader("Detailed Results")

                    for check in data["checks"]:
                        if check["status"] == "PASS":
                            st.success(
                                f"✅ **{check['ingredient'].title()}** ({check['amount']})  \n"
                                f"{check['message']}"
                            )
                        elif check["status"] == "WARNING":
                            st.warning(
                                f"⚠️ **{check['ingredient'].title()}** ({check['amount']})  \n"
                                f"{check['message']}"
                            )
                            if check.get("recommendation"):
                                st.markdown(f"> 💡 **Recommendation:** {check['recommendation']}")
                        else:
                            st.error(
                                f"❌ **{check['ingredient'].title()}** ({check['amount']})  \n"
                                f"{check['message']}"
                            )
                            if check.get("recommendation"):
                                st.markdown(f"> 💡 **Recommendation:** {check['recommendation']}")

                        if check.get("standard"):
                            st.caption(f"Reference: {check['standard']}")

                        st.write("")

                except Exception as e:
                    st.error(f"Backend error: {e}")
