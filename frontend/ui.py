import streamlit as st
import requests

API_URL = "http://localhost:8000"

st.set_page_config(page_title="FSANZ Regulatory Assistant", layout="wide")
st.title("FSANZ Regulatory Affairs Assistant")
st.caption("Powered by FSANZ Food Standards Code, March 2025")


# ════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — defined first so all tabs can use them
# ════════════════════════════════════════════════════════════

def _display_checks(checks: list, mode: str):
    for check in checks:
        label  = check.get("ingredient", check.get("requirement", "Item")).title()
        amount = f" ({check['amount']})" if mode == "ingredients" and check.get("amount") else ""

        if check["status"] == "PASS":
            st.success(f"✅ **{label}**{amount}  \n{check['message']}")
        elif check["status"] == "WARNING":
            st.warning(f"⚠️ **{label}**{amount}  \n{check['message']}")
            if check.get("recommendation"):
                st.markdown(f"> 💡 **Recommendation:** {check['recommendation']}")
        else:
            st.error(f"❌ **{label}**{amount}  \n{check['message']}")
            if check.get("recommendation"):
                st.markdown(f"> 💡 **Recommendation:** {check['recommendation']}")

        if check.get("standard"):
            st.caption(f"Reference: {check['standard']}")
        st.write("")


def _display_compliance_results(data: dict, mode: str):
    st.divider()
    if data["overall_status"] == "PASS":
        st.success(f"✅ OVERALL STATUS: COMPLIANT — {data['summary']}")
    elif data["overall_status"] == "WARNING":
        st.warning(f"⚠️ OVERALL STATUS: REVIEW REQUIRED — {data['summary']}")
    elif data["overall_status"] == "FAIL":
        st.error(f"❌ OVERALL STATUS: NON-COMPLIANT — {data['summary']}")
    else:
        st.error(f"ERROR — {data['summary']}")

    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Checked", data["total_checks"])
    col2.metric("Passed",        data["passed"])
    col3.metric("Warnings",      data["warnings"])
    col4.metric("Failed",        data["failed"])

    st.divider()
    st.subheader("Detailed Results")
    _display_checks(data["checks"], mode=mode)

# ── Sidebar ─────────────────────────────────────────────────
with st.sidebar:
    st.header("Chat — Try These Questions")
    examples = [
        "Is potassium sorbate allowed in fruit juice?",
        "What allergens must be declared on labels?",
        "What are the NIP requirements for beverages?",
        "What is the maximum sulphur dioxide level in wine?",
        "What warning statements are required for high caffeine drinks?"
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state["prefill"] = ex

    st.divider()
    st.header("Compliance — Try This Example")
    sample = "Filtered water, apple juice (30%), raspberry juice (8%), sugar (45g/kg), natural flavour, potassium sorbate (200mg/kg)"
    if st.button("Load sample ingredient list", use_container_width=True):
        st.session_state["compliance_input"] = sample

    st.divider()
    st.markdown("**How it works**")
    st.markdown("""
- **Chat Tab** → Ask any FSANZ regulatory question
- **Ingredients Tab** → Check ingredients via text or image
- **Labelling Tab** → Check your product label via form
- **Combined Tab** → Full compliance check in one go
- All queries are logged to AWS S3
""")

# ── Tabs ─────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "💬 Chat Assistant",
    "🧪 Ingredients Compliance",
    "🏷️ Labelling Compliance",
    "✅ Combined Compliance"
])


# ════════════════════════════════════════════════════════════
# TAB 1 — CHAT
# ════════════════════════════════════════════════════════════
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
                    res  = requests.post(f"{API_URL}/ask", json={"question": user_input}, timeout=30)
                    data = res.json()
                    st.markdown(data["answer"])
                    st.caption(f"Source: {data['source']} | Pages: {data['pages_referenced']}")
                    st.session_state.messages.append({"role": "assistant", "content": data["answer"]})
                except Exception as e:
                    st.error(f"Backend error: {e}")


# ════════════════════════════════════════════════════════════
# TAB 2 — INGREDIENTS COMPLIANCE
# ════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Ingredients Compliance Checker")
    st.markdown("Check your product ingredients against the FSANZ Food Standards Code. Type your ingredient list or upload a photo of your food label.")

    input_method = st.radio(
        "Choose input method:",
        ["Type / Paste Ingredients", "Upload Ingredient Label Image"],
        horizontal=True,
        key="ing_input_method"
    )

    ingredient_input = ""
    uploaded_image   = None

    if input_method == "Type / Paste Ingredients":
        default_input    = st.session_state.pop("compliance_input", "")
        ingredient_input = st.text_area(
            "Paste your ingredient list here",
            value=default_input,
            placeholder="e.g. Filtered water, apple juice (30%), sugar (45g/kg), natural flavour, potassium sorbate (200mg/kg)",
            height=120,
            key="ing_text"
        )
    else:
        st.session_state.pop("compliance_input", None)
        uploaded_image = st.file_uploader(
            "Upload a photo of your food product label",
            type=["jpg", "jpeg", "png", "webp"],
            key="ing_image"
        )
        if uploaded_image:
            st.image(uploaded_image, caption="Uploaded label", width=400)
            st.success("Image uploaded. Click Check Ingredients to analyse.")

    if st.button("Check Ingredients", type="primary", use_container_width=True, key="btn_ing"):
        if input_method == "Type / Paste Ingredients" and not ingredient_input.strip():
            st.warning("Please enter an ingredient list first.")
        elif input_method == "Upload Ingredient Label Image" and uploaded_image is None:
            st.warning("Please upload an image first.")
        else:
            with st.spinner("Checking ingredients against FSANZ Code... Please wait."):
                try:
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
                    _display_compliance_results(data, mode="ingredients")
                except Exception as e:
                    st.error(f"Backend error: {e}")


# ════════════════════════════════════════════════════════════
# TAB 3 — LABELLING COMPLIANCE
# ════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Labelling Compliance Checker")
    st.markdown("Fill in the details about your product label. The system will check whether it meets all FSANZ labelling requirements.")

    with st.form("labelling_form"):
        col1, col2 = st.columns(2)

        with col1:
            product_name     = st.text_input("Product Name", placeholder="e.g. Tropical Fruit Juice")
            product_category = st.selectbox("Product Category", [
                "Fruit and Vegetable Juice",
                "Dairy Products",
                "Meat and Meat Products",
                "Bakery Products",
                "Beverages",
                "Snack Foods",
                "Confectionery",
                "Cereal Products",
                "Seafood",
                "Other"
            ])
            has_ingredients_list = st.radio("Ingredients List Present?", ["Yes", "No"], horizontal=True, key="lbl_ing")
            has_nip              = st.radio("Nutrition Information Panel (NIP) Present?", ["Yes", "No"], horizontal=True, key="lbl_nip")

        with col2:
            has_date_marking        = st.radio("Date Marking Present? (Best Before / Use By)", ["Yes", "No"], horizontal=True, key="lbl_date")
            has_country_of_origin   = st.radio("Country of Origin Labelling Present?", ["Yes", "No"], horizontal=True, key="lbl_coo")
            has_allergen_declaration = st.radio("Allergen Declarations Present?", ["Yes", "No"], horizontal=True, key="lbl_allergen")
            allergens               = st.text_input("List Allergens Present (if any)", placeholder="e.g. wheat, milk, eggs, soy")
            has_warning_statements  = st.radio("Warning Statements Present (if required)?", ["Yes", "No", "Not Applicable"], horizontal=True, key="lbl_warn")

        additional_notes = st.text_area("Additional Notes (optional)", placeholder="Any other label details...", height=80)
        submitted        = st.form_submit_button("Check Labelling", type="primary", use_container_width=True)

    if submitted:
        if not product_name.strip():
            st.warning("Please enter a product name.")
        else:
            with st.spinner("Checking labelling requirements against FSANZ Code..."):
                try:
                    payload = {
                        "product_name":            product_name,
                        "product_category":        product_category,
                        "has_ingredients_list":    has_ingredients_list,
                        "has_nip":                 has_nip,
                        "has_date_marking":        has_date_marking,
                        "has_country_of_origin":   has_country_of_origin,
                        "has_allergen_declaration": has_allergen_declaration,
                        "allergens":               allergens,
                        "has_warning_statements":  has_warning_statements,
                        "additional_notes":        additional_notes
                    }
                    res  = requests.post(f"{API_URL}/check-labelling", json=payload, timeout=180)
                    data = res.json()
                    _display_compliance_results(data, mode="labelling")
                except Exception as e:
                    st.error(f"Backend error: {e}")


# ════════════════════════════════════════════════════════════
# TAB 4 — COMBINED COMPLIANCE
# ════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Combined Compliance Checker")
    st.markdown("Run a full FSANZ compliance check covering both ingredients and labelling in one go.")

    # Input method
    comb_input_method = st.radio(
        "How would you like to provide your ingredients?",
        ["Type / Paste Ingredients", "Upload Ingredient Label Image"],
        horizontal=True,
        key="comb_input_method"
    )

    comb_ingredient_input = ""
    comb_uploaded_image   = None

    if comb_input_method == "Type / Paste Ingredients":
        comb_ingredient_input = st.text_area(
            "Paste your ingredient list here",
            placeholder="e.g. Filtered water, apple juice (30%), sugar (45g/kg), natural flavour, potassium sorbate (200mg/kg)",
            height=100,
            key="comb_text"
        )
    else:
        comb_uploaded_image = st.file_uploader(
            "Upload a photo of your food product label",
            type=["jpg", "jpeg", "png", "webp"],
            key="comb_image"
        )
        if comb_uploaded_image:
            st.image(comb_uploaded_image, caption="Uploaded label", width=400)

    st.divider()
    st.markdown("**Product Label Details**")

    with st.form("combined_form"):
        col1, col2 = st.columns(2)

        with col1:
            comb_product_name     = st.text_input("Product Name", placeholder="e.g. Tropical Fruit Juice", key="comb_pname")
            comb_product_category = st.selectbox("Product Category", [
                "Fruit and Vegetable Juice", "Dairy Products", "Meat and Meat Products",
                "Bakery Products", "Beverages", "Snack Foods", "Confectionery",
                "Cereal Products", "Seafood", "Other"
            ], key="comb_pcat")
            comb_has_ing_list = st.radio("Ingredients List Present?", ["Yes", "No"], horizontal=True, key="comb_ing")
            comb_has_nip      = st.radio("Nutrition Information Panel Present?", ["Yes", "No"], horizontal=True, key="comb_nip")

        with col2:
            comb_has_date     = st.radio("Date Marking Present?", ["Yes", "No"], horizontal=True, key="comb_date")
            comb_has_coo      = st.radio("Country of Origin Present?", ["Yes", "No"], horizontal=True, key="comb_coo")
            comb_has_allergen = st.radio("Allergen Declarations Present?", ["Yes", "No"], horizontal=True, key="comb_alg")
            comb_allergens    = st.text_input("List Allergens Present (if any)", placeholder="e.g. wheat, milk, soy", key="comb_alg_list")
            comb_has_warn     = st.radio("Warning Statements Present?", ["Yes", "No", "Not Applicable"], horizontal=True, key="comb_warn")

        comb_notes    = st.text_area("Additional Notes (optional)", height=60, key="comb_notes")
        comb_submitted = st.form_submit_button("Run Full Compliance Check", type="primary", use_container_width=True)

    if comb_submitted:
        if comb_input_method == "Type / Paste Ingredients" and not comb_ingredient_input.strip():
            st.warning("Please enter an ingredient list.")
        elif comb_input_method == "Upload Ingredient Label Image" and comb_uploaded_image is None:
            st.warning("Please upload an image.")
        elif not comb_product_name.strip():
            st.warning("Please enter a product name.")
        else:
            with st.spinner("Running full compliance check... This may take a moment."):
                try:
                    if comb_input_method == "Upload Ingredient Label Image":
                        image_bytes = comb_uploaded_image.read()
                        res = requests.post(
                            f"{API_URL}/check-combined-image",
                            files={"file": (comb_uploaded_image.name, image_bytes, comb_uploaded_image.type)},
                            data={
                                "product_name": comb_product_name, "product_category": comb_product_category,
                                "has_ingredients_list": comb_has_ing_list, "has_nip": comb_has_nip,
                                "has_date_marking": comb_has_date, "has_country_of_origin": comb_has_coo,
                                "has_allergen_declaration": comb_has_allergen, "allergens": comb_allergens,
                                "has_warning_statements": comb_has_warn, "additional_notes": comb_notes
                            },
                            timeout=300
                        )
                    else:
                        payload = {
                            "ingredient_text": comb_ingredient_input,
                            "product_name": comb_product_name, "product_category": comb_product_category,
                            "has_ingredients_list": comb_has_ing_list, "has_nip": comb_has_nip,
                            "has_date_marking": comb_has_date, "has_country_of_origin": comb_has_coo,
                            "has_allergen_declaration": comb_has_allergen, "allergens": comb_allergens,
                            "has_warning_statements": comb_has_warn, "additional_notes": comb_notes
                        }
                        res = requests.post(f"{API_URL}/check-combined", json=payload, timeout=300)

                    data = res.json()

                    # Overall banner
                    st.divider()
                    if data["overall_status"] == "PASS":
                        st.success(f"✅ OVERALL: FULLY COMPLIANT — {data['summary']}")
                    elif data["overall_status"] == "WARNING":
                        st.warning(f"⚠️ OVERALL: REVIEW REQUIRED — {data['summary']}")
                    else:
                        st.error(f"❌ OVERALL: NON-COMPLIANT — {data['summary']}")

                    # Summary metrics
                    st.divider()
                    st.markdown("#### Ingredients Summary")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Total Ingredients", data["total_ingredient_checks"])
                    c2.metric("Passed",   data["ingredients_passed"])
                    c3.metric("Warnings", data["ingredients_warnings"])
                    c4.metric("Failed",   data["ingredients_failed"])

                    st.markdown("#### Labelling Summary")
                    c5, c6, c7, c8 = st.columns(4)
                    c5.metric("Total Checks", data["total_labelling_checks"])
                    c6.metric("Passed",   data["labelling_passed"])
                    c7.metric("Warnings", data["labelling_warnings"])
                    c8.metric("Failed",   data["labelling_failed"])

                    # Detailed results
                    st.divider()
                    st.markdown("#### Ingredient Results")
                    _display_checks(data["ingredients_report"]["checks"], mode="ingredients")

                    st.divider()
                    st.markdown("#### Labelling Results")
                    _display_checks(data["labelling_report"]["checks"], mode="labelling")

                except Exception as e:
                    st.error(f"Backend error: {e}")
