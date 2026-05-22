import os
import streamlit as st
import streamlit.components.v1 as components
import requests

API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="FSANZ Regulatory Assistant", layout="wide")
st.title("FSANZ Regulatory Affairs Assistant")
st.caption("Powered by FSANZ Food Standards Code, March 2025")

# ── Session state defaults ───────────────────────────────────
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "label_payload" not in st.session_state:
    st.session_state["label_payload"] = None
if "generated_label_html" not in st.session_state:
    st.session_state["generated_label_html"] = None


# ════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════

def _display_checks(checks: list, mode: str):
    for check in checks:
        if mode == "ingredients":
            label = check.get("ingredient", "Item").title()
            amount = f" ({check['amount']})" if check.get("amount") else ""
        elif mode == "label":
            label = check.get("label", check.get("field", "Item"))
            amount = ""
        elif mode == "claims":
            label = check.get("claim", "Claim")
            amount = ""
        else:
            label = check.get("requirement", "Item")
            amount = ""

        status = check.get("status", "WARNING")

        if status in ("PASS", "APPROVED"):
            st.success(f"✅ **{label}**{amount}  \n{check.get('message', '')}")
        elif status == "WARNING":
            st.warning(f"⚠️ **{label}**{amount}  \n{check.get('message', '')}")
            if check.get("recommendation"):
                st.markdown(f"> 💡 **Recommendation:** {check['recommendation']}")
        else:
            st.error(f"❌ **{label}**{amount}  \n{check.get('message', '')}")
            if check.get("recommendation"):
                st.markdown(f"> 💡 **Recommendation:** {check['recommendation']}")

        if check.get("standard"):
            st.caption(f"Reference: {check['standard']}")
        st.write("")


def _display_compliance_results(data: dict, mode: str):
    st.divider()
    overall = data.get("overall_status", "")
    summary = data.get("summary", "")
    if overall == "PASS":
        st.success(f"✅ OVERALL STATUS: COMPLIANT — {summary}")
    elif overall == "WARNING":
        st.warning(f"⚠️ OVERALL STATUS: REVIEW REQUIRED — {summary}")
    elif overall == "FAIL":
        st.error(f"❌ OVERALL STATUS: NON-COMPLIANT — {summary}")
    else:
        st.error(f"ERROR — {summary}")

    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Checked", data.get("total_checks", 0))
    col2.metric("Passed",        data.get("passed", 0))
    col3.metric("Warnings",      data.get("warnings", 0))
    col4.metric("Failed",        data.get("failed", 0))

    st.divider()
    st.subheader("Detailed Results")
    _display_checks(data.get("checks", []), mode=mode)


# ── Sidebar ──────────────────────────────────────────────────
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
- **Chat** → Ask any FSANZ regulatory question
- **Compliance** → Check ingredients via text or image
- **Labelling** → Check label fields + generate label
- **Nutrition Claims** → Validate claims against FSANZ
- All queries are logged to AWS S3
""")

# ── Tabs ─────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "💬 Chat Assistant",
    "🧪 Compliance Checker",
    "🏷️ Labelling Compliance",
    "🥗 Nutrition Claims"
])


# ════════════════════════════════════════════════════════════
# TAB 1 — CHAT
# ════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Ask a Regulatory Question")

    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prefill    = st.session_state.pop("prefill", "")
    user_input = st.chat_input("Ask a regulatory question...") or prefill

    if user_input:
        st.session_state["messages"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Searching FSANZ Code..."):
                try:
                    res = requests.post(f"{API_URL}/ask", json={"question": user_input}, timeout=60)
                    if res.status_code != 200:
                        st.error(f"Backend error {res.status_code}: {res.text}")
                    else:
                        data = res.json()
                        st.markdown(data.get("answer", "No answer returned."))
                        st.caption(f"Source: {data.get('source', '')} | Pages: {data.get('pages_referenced', [])}")
                        st.session_state["messages"].append({"role": "assistant", "content": data.get("answer", "")})
                except Exception as e:
                    st.error(f"Connection error: {e}")


# ════════════════════════════════════════════════════════════
# TAB 2 — COMPLIANCE CHECKER
# ════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Ingredients Compliance Checker")
    st.markdown("Check your product ingredients against the FSANZ Food Standards Code. Type your ingredient list or upload a photo of your food label.")

    input_method = st.radio(
        "Choose input method:",
        ["Type / Paste Ingredients", "Upload Ingredient Label Image"],
        horizontal=True,
        key="compliance_input_method"
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
                    if res.status_code != 200:
                        st.error(f"Backend error {res.status_code}: {res.text}")
                    else:
                        data = res.json()
                        _display_compliance_results(data, mode="ingredients")
                except Exception as e:
                    st.error(f"Connection error: {e}")


# ════════════════════════════════════════════════════════════
# TAB 3 — LABELLING COMPLIANCE + LABEL GENERATOR
# ════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Labelling Compliance Checker")
    st.markdown("Enter your 10 label fields. The tool checks each against FSANZ requirements and can generate a print-ready label.")

    with st.form("label_form"):
        st.markdown("#### Product Details")
        col1, col2 = st.columns(2)
        with col1:
            f_product_name          = st.text_input("Product Name *", placeholder="e.g. Raspberry Blast Fruit Drink")
            f_net_weight_volume     = st.text_input("Net Weight / Volume *", placeholder="e.g. 500mL")
            f_business_name_address = st.text_input("Business Name & Address *", placeholder="e.g. Fresh Foods Pty Ltd, 12 Market Street, Sydney NSW 2000")
            f_country_of_origin     = st.text_input("Country of Origin", placeholder="e.g. Made in Australia from at least 80% Australian ingredients")
            f_date_marking          = st.text_input("Date Marking", placeholder="e.g. Best Before: 30 Jun 2025")
        with col2:
            f_storage_instructions  = st.text_input("Storage Instructions", placeholder="e.g. Keep refrigerated below 4°C. Once opened consume within 3 days.")
            f_lot_identification    = st.text_input("Lot Identification", placeholder="e.g. Lot No: A2025-042")
            f_allergen_declaration  = st.text_area("Allergen Declaration", placeholder="e.g. Contains no allergens. May be produced in a facility that handles tree nuts.", height=80)

        st.markdown("#### Ingredient List")
        f_ingredient_list = st.text_area(
            "Ingredients (in descending order of weight)",
            placeholder="e.g. Water, Apple Juice (30%), Raspberry Juice (8%), Sugar (45g/kg), Natural Flavour, Potassium Sorbate (200mg/kg)",
            height=80
        )

        st.markdown("#### Nutrition Information Panel")
        f_nutrition_information = st.text_area(
            "Paste your NIP values",
            placeholder="e.g. Energy 450kJ, Protein 0.5g, Fat 0g, Saturated Fat 0g, Carbohydrate 26.3g, Sugars 26.3g, Sodium 20mg, Vitamin C 112mg — per 250mL serve",
            height=100
        )

        submitted = st.form_submit_button("Check Label Compliance", type="primary", use_container_width=True)

    if submitted:
        if not f_product_name.strip():
            st.warning("Product Name is required.")
        else:
            label_payload = {
                "product_name":          f_product_name,
                "business_name_address": f_business_name_address,
                "ingredient_list":       f_ingredient_list,
                "allergen_declaration":  f_allergen_declaration,
                "nutrition_information": f_nutrition_information,
                "country_of_origin":     f_country_of_origin,
                "storage_instructions":  f_storage_instructions,
                "net_weight_volume":     f_net_weight_volume,
                "date_marking":          f_date_marking,
                "lot_identification":    f_lot_identification,
            }
            st.session_state["label_payload"] = label_payload
            st.session_state["generated_label_html"] = None

            with st.spinner("Checking label against FSANZ Code..."):
                try:
                    res = requests.post(f"{API_URL}/check-label", json=label_payload, timeout=180)
                    if res.status_code != 200:
                        st.error(f"Backend error {res.status_code}: {res.text}")
                    else:
                        data = res.json()
                        _display_compliance_results(data, mode="label")

                        if data.get("next_steps"):
                            st.subheader("📋 Recommended Next Steps")
                            for i, step in enumerate(data["next_steps"], 1):
                                st.markdown(f"{i}. {step}")
                except Exception as e:
                    st.error(f"Connection error: {e}")

    # ── Label Generator ──────────────────────────────────────
    if st.session_state["label_payload"]:
        st.divider()
        st.subheader("🖨️ Generate Print-Ready Label")
        st.markdown("Generate a formatted food label based on the fields you entered above.")

        if st.button("Generate Label", type="secondary", use_container_width=True, key="btn_generate_label"):
            with st.spinner("Generating your label..."):
                try:
                    res = requests.post(
                        f"{API_URL}/generate-label",
                        json=st.session_state["label_payload"],
                        timeout=120
                    )
                    if res.status_code != 200:
                        st.error(f"Backend error {res.status_code}: {res.text}")
                    else:
                        st.session_state["generated_label_html"] = res.json().get("html", "")
                except Exception as e:
                    st.error(f"Connection error: {e}")

        if st.session_state["generated_label_html"]:
            st.success("Label generated successfully!")
            components.html(st.session_state["generated_label_html"], height=900, scrolling=True)
            st.download_button(
                label="⬇️ Download Label as HTML",
                data=st.session_state["generated_label_html"],
                file_name=f"{st.session_state['label_payload'].get('product_name', 'label').replace(' ', '_')}_label.html",
                mime="text/html",
                use_container_width=True
            )


# ════════════════════════════════════════════════════════════
# TAB 4 — NUTRITION CLAIMS VALIDATOR
# ════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Nutrition Claims Validator")
    st.markdown("Paste your NIP values and tick the claims you want to make. The tool checks each claim against FSANZ Standard 1.2.7 thresholds.")

    with st.form("nutrition_claims_form"):
        st.markdown("#### Product Details")
        col1, col2 = st.columns(2)
        with col1:
            nc_product_name = st.text_input("Product Name", placeholder="e.g. Raspberry Blast Fruit Drink")
        with col2:
            nc_product_type = st.text_input("Product Type", placeholder="e.g. Fruit drink, beverage")

        st.markdown("#### Nutrition Information Panel")
        nc_nip_text = st.text_area(
            "Paste your NIP values here",
            placeholder=(
                "e.g.\n"
                "Energy: 450kJ per serve, 180kJ per 100mL\n"
                "Protein: 0.5g per serve, 0.2g per 100mL\n"
                "Fat: 0g per serve, 0g per 100mL\n"
                "Saturated Fat: 0g\n"
                "Carbohydrate: 26.3g per serve, 10.5g per 100mL\n"
                "Sugars: 26.3g per serve, 10.5g per 100mL\n"
                "Sodium: 20mg per serve, 8mg per 100mL\n"
                "Vitamin C: 112mg per serve, 45mg per 100mL"
            ),
            height=180
        )

        st.markdown("#### Select Claims to Validate")
        claims_col1, claims_col2, claims_col3 = st.columns(3)
        with claims_col1:
            c_low_fat        = st.checkbox("Low Fat")
            c_reduced_fat    = st.checkbox("Reduced Fat")
            c_low_sugar      = st.checkbox("Low Sugar / Low in Sugars")
            c_no_added_sugar = st.checkbox("No Added Sugar")
        with claims_col2:
            c_low_sodium  = st.checkbox("Low Sodium / Low Salt")
            c_high_fibre  = st.checkbox("High Fibre")
            c_good_fibre  = st.checkbox("Good Source of Fibre")
            c_high_protein = st.checkbox("High Protein")
        with claims_col3:
            c_vit_c    = st.checkbox("High in Vitamin C")
            c_calcium  = st.checkbox("Source of Calcium")
            c_light    = st.checkbox("Light / Lite")
            c_diet     = st.checkbox("Diet")

        nc_submitted = st.form_submit_button("Validate Claims", type="primary", use_container_width=True)

    if nc_submitted:
        selected_claims = [
            claim for claim, selected in [
                ("Low Fat",              c_low_fat),
                ("Reduced Fat",          c_reduced_fat),
                ("Low Sugar",            c_low_sugar),
                ("No Added Sugar",       c_no_added_sugar),
                ("Low Sodium",           c_low_sodium),
                ("High Fibre",           c_high_fibre),
                ("Good Source of Fibre", c_good_fibre),
                ("High Protein",         c_high_protein),
                ("High in Vitamin C",    c_vit_c),
                ("Source of Calcium",    c_calcium),
                ("Light / Lite",         c_light),
                ("Diet",                 c_diet),
            ] if selected
        ]

        if not nc_nip_text.strip():
            st.warning("Please paste your NIP values.")
        elif not selected_claims:
            st.warning("Please select at least one claim to validate.")
        else:
            with st.spinner("Validating claims against FSANZ thresholds..."):
                try:
                    res = requests.post(
                        f"{API_URL}/check-nutrition-claims",
                        json={
                            "product_name":    nc_product_name,
                            "product_type":    nc_product_type,
                            "nip_text":        nc_nip_text,
                            "selected_claims": selected_claims,
                        },
                        timeout=180
                    )
                    if res.status_code != 200:
                        st.error(f"Backend error {res.status_code}: {res.text}")
                    else:
                        data = res.json()
                        st.divider()
                        overall = data.get("overall_status", "")
                        msg     = data.get("overall_message", "")
                        if overall == "COMPLIANT":
                            st.success(f"✅ {overall} — {msg}")
                        elif overall == "MOSTLY COMPLIANT":
                            st.warning(f"⚠️ {overall} — {msg}")
                        else:
                            st.error(f"❌ {overall} — {msg}")

                        st.divider()
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Total Claims",  data.get("total_claims", 0))
                        col2.metric("Approved",      data.get("approved", 0))
                        col3.metric("Warnings",      data.get("warnings", 0))
                        col4.metric("Rejected",      data.get("rejected", 0))

                        st.divider()
                        st.subheader("Claim Results")
                        for result in data.get("results", []):
                            status = result.get("status", "WARNING")
                            claim  = result.get("claim", "")
                            if status == "APPROVED":
                                st.success(f"✅ **{claim}**  \n{result.get('message', '')}")
                            elif status == "WARNING":
                                st.warning(f"⚠️ **{claim}**  \n{result.get('message', '')}")
                                if result.get("recommendation"):
                                    st.markdown(f"> 💡 {result['recommendation']}")
                            else:
                                st.error(f"❌ **{claim}**  \n{result.get('message', '')}")
                                if result.get("recommendation"):
                                    st.markdown(f"> 💡 {result['recommendation']}")
                            st.caption(
                                f"Your value: {result.get('user_value', '—')}  |  "
                                f"FSANZ threshold: {result.get('fsanz_threshold', '—')}  |  "
                                f"Ref: {result.get('standard', '')}"
                            )
                            st.write("")
                except Exception as e:
                    st.error(f"Connection error: {e}")
