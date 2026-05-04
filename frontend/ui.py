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
    st.markdown("Check your product ingredient list against the FSANZ Food Standards Code. Type your ingredients **or** upload a photo of your food label.")

    # --- Input Method Toggle ---
    input_method = st.radio(
        "How would you like to provide your ingredients?",
        ["Type / Paste Ingredients", "Upload Ingredient Label Image"],
        horizontal=True
    )

    ingredient_input = ""
    uploaded_image   = None

    if input_method == "Type / Paste Ingredients":
        default_input    = st.session_state.pop("compliance_input", "")
        ingredient_input = st.text_area(
            "Paste your ingredient list here",
            value=default_input,
            placeholder="e.g. Filtered water, apple juice (30%), sugar (45g/kg), natural flavour, potassium sorbate (200mg/kg)",
            height=120
        )

    else:
        st.session_state.pop("compliance_input", None)
        uploaded_image = st.file_uploader(
            "Upload a photo of your food product label",
            type=["jpg", "jpeg", "png", "webp"],
            help="Take a clear photo of the ingredients list on the food packaging"
        )
        if uploaded_image:
            st.image(uploaded_image, caption="Uploaded label", width=400)
            st.success("Image uploaded. Click Check Compliance to extract and check ingredients.")

    st.write("")
    if st.button("Check Compliance", type="primary", use_container_width=True):

        # Validate input
        if input_method == "Type / Paste Ingredients" and not ingredient_input.strip():
            st.warning("Please enter an ingredient list first.")
        elif input_method == "Upload Ingredient Label Image" and uploaded_image is None:
            st.warning("Please upload an image first.")
        else:
            with st.spinner("Analysing ingredients against FSANZ Code... Please wait."):
                try:
                    # Call correct endpoint based on input method
                    if input_method == "Upload Ingredient Label Image":
                        image_bytes = uploaded_image.read()
                        res = requests.post(
                            f"{API_URL}/check-compliance-image",
                            files={"file": (uploaded_image.name, image_bytes, uploaded_image.type)},
                            timeout=180
                        )
                    else:
                        res = requests.post(
                            f"{API_URL}/check-compliance",
                            json={"ingredient_text": ingredient_input},
                            timeout=180
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
