import os
import re
import json
import base64
from datetime import datetime
from dotenv import load_dotenv
import anthropic
import boto3
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

load_dotenv(dotenv_path="../.env", override=True)

claude          = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
s3              = boto3.client('s3', region_name=os.getenv("AWS_REGION"))
BUCKET          = os.getenv("S3_BUCKET")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
pc              = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
pinecone_index  = pc.Index("fsanz-index")

# Load E-number mapping
_enumber_map_path = os.path.join(os.path.dirname(__file__), "enumber_map.json")
with open(_enumber_map_path, "r", encoding="utf-8") as f:
    ENUMBER_MAP = json.load(f)
# Build lowercase lookup
ENUMBER_LOOKUP = {k.lower(): v for k, v in ENUMBER_MAP.items()}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def normalise_ingredient_name(name: str) -> str:
    """
    Convert E-numbers, INS codes, and American spellings to standard FSANZ names.
    e.g. E202 -> potassium sorbate, sulfur -> sulphur
    """
    name_lower = name.lower().strip()

    # Check E-number map
    if name_lower in ENUMBER_LOOKUP:
        return ENUMBER_LOOKUP[name_lower]

    # Check partial match for E-numbers like "E202 (potassium sorbate)"
    for key, value in ENUMBER_LOOKUP.items():
        if key in name_lower:
            return value

    # Fix American spelling to Australian
    spelling_fixes = {
        "sulfur":    "sulphur",
        "sulfite":   "sulphite",
        "sulfate":   "sulphate",
        "flavor":    "flavour",
        "colour":    "colour",
        "color":     "colour",
        "aluminum":  "aluminium",
        "fiber":     "fibre",
        "center":    "centre",
    }
    for american, australian in spelling_fixes.items():
        name_lower = name_lower.replace(american, australian)

    return name_lower

def extract_json(text: str):
    """Robustly extract JSON from Claude response"""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except:
        pass
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass
    raise ValueError(f"Could not extract JSON: {text[:200]}")


def get_fsanz_context(query: str, top_k: int = 8) -> str:
    """Search Pinecone for relevant FSANZ content"""
    vector  = embedding_model.encode(query).tolist()
    results = pinecone_index.query(vector=vector, top_k=top_k, include_metadata=True)
    return "\n\n---\n\n".join([r["metadata"]["text"] for r in results["matches"]])


def log_to_s3(folder: str, data: dict):
    """Save any report to S3"""
    key = f"{folder}/{datetime.utcnow().strftime('%Y-%m-%d')}/{datetime.utcnow().strftime('%H-%M-%S')}.json"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(data, indent=2).encode('utf-8'),
        ContentType='application/json'
    )
    print(f"Logged to S3: {key}")


# ─────────────────────────────────────────────
# MODULE 1 — INGREDIENTS COMPLIANCE
# ─────────────────────────────────────────────

def extract_ingredients_from_text(ingredient_text: str) -> list:
    """Extract ingredients from plain text using Claude, then normalise names"""
    prompt = f"""Extract all ingredients and amounts from this list.
Return ONLY a JSON array. No explanation. No markdown.
Format: [{{"ingredient": "sugar", "amount": "45g/kg"}}, {{"ingredient": "water", "amount": "not specified"}}]
If amount not given use "not specified".
Convert E-numbers to full names e.g. E202 becomes potassium sorbate.
Convert American spelling to Australian e.g. sulfur becomes sulphur, flavor becomes flavour.

Ingredient list: {ingredient_text}"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        ingredients = extract_json(response.content[0].text)
        # Apply local E-number normalisation on top of Claude's extraction
        for item in ingredients:
            item["ingredient"] = normalise_ingredient_name(item["ingredient"])
        return ingredients
    except:
        return []


def extract_ingredients_from_image(image_bytes: bytes, media_type: str) -> list:
    """Extract ingredients from food label image using Claude Vision"""
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    prompt = """Look at this food product label. Extract ALL ingredients and amounts.
Return ONLY a JSON array. No markdown. No explanation.
Format: [{"ingredient": "sugar", "amount": "45g/kg"}, {"ingredient": "water", "amount": "not specified"}]
Convert E-numbers to full names. Convert American spelling to Australian spelling.
If no ingredients found return: []"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
            {"type": "text", "text": prompt}
        ]}]
    )
    try:
        return extract_json(response.content[0].text)
    except:
        return []


def check_all_ingredients(ingredients: list) -> list:
    """Check all ingredients against FSANZ in one Claude call"""
    context = get_fsanz_context(
        "FSANZ permitted levels additives preservatives allergens colours " +
        " ".join([i["ingredient"] for i in ingredients])
    )

    numbered = "\n".join([
        f"{i+1}. {item['ingredient']} — amount: {item['amount']}"
        for i, item in enumerate(ingredients)
    ])

    prompt = f"""You are a FSANZ compliance expert for Australia and New Zealand.
Check each ingredient below against the FSANZ Food Standards Code.

FSANZ CONTEXT (from FSANZ Food Standards Code):
{context}

INGREDIENTS:
{numbered}

IMPORTANT RULES:
- Use the FSANZ context above as your PRIMARY source
- If an ingredient is not found in the context, use your general knowledge of FSANZ regulations to provide guidance
- If using general knowledge instead of the context, set standard to "General FSANZ Knowledge" and mention this in the message
- Treat sulphur and sulfur as the same ingredient
- Treat flavour and flavor as the same ingredient
- American and Australian spelling variations should be treated as identical

Return a JSON array with one object per ingredient. Raw JSON only — no markdown.
[
  {{
    "ingredient": "name",
    "status": "PASS",
    "message": "one sentence explanation — mention if based on general knowledge not specific FSANZ clause",
    "standard": "Standard X.X.X or Schedule X or General FSANZ Knowledge",
    "recommendation": ""
  }}
]

Status rules:
- PASS: within FSANZ limits or no restrictions found
- WARNING: allergen needs label declaration, near limit, amount unclear, conditional, or not found in FSANZ
- FAIL: clearly exceeds maximum permitted level or explicitly not permitted under FSANZ"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    print(f"[check_ingredients] Response: {raw[:300]}")

    try:
        result = extract_json(raw)
        if isinstance(result, dict):
            result = [result]
        return result
    except Exception as e:
        print(f"[check_ingredients] Parse error: {e}")
        return [{"ingredient": i["ingredient"], "status": "WARNING",
                 "message": "Could not determine compliance. Manual review recommended.",
                 "standard": "FSANZ Food Standards Code", "recommendation": "Please consult the FSANZ Food Standards Code."}
                for i in ingredients]


def run_ingredients_compliance(ingredient_text: str, image_bytes: bytes = None, media_type: str = None) -> dict:
    """Run ingredients compliance check — text or image input"""
    print("Running ingredients compliance check...")

    ingredients = extract_ingredients_from_image(image_bytes, media_type) if image_bytes else extract_ingredients_from_text(ingredient_text)
    print(f"Extracted {len(ingredients)} ingredients")

    if not ingredients:
        return {"overall_status": "ERROR", "ingredient_text": ingredient_text, "checks": [],
                "total_checks": 0, "passed": 0, "warnings": 0, "failed": 0,
                "summary": "Could not extract ingredients. Please check your input."}

    verdicts = check_all_ingredients(ingredients)
    checks, overall = [], "PASS"

    for i, item in enumerate(ingredients):
        verdict = verdicts[i] if i < len(verdicts) else {"status": "WARNING", "message": "Not checked.", "standard": "", "recommendation": ""}
        status  = verdict.get("status", "WARNING").upper()
        if status not in ["PASS", "WARNING", "FAIL"]:
            status = "WARNING"
        checks.append({"ingredient": item["ingredient"], "amount": item.get("amount", "not specified"),
                        "status": status, "message": verdict.get("message", ""),
                        "standard": verdict.get("standard", ""), "recommendation": verdict.get("recommendation", "")})
        if status == "FAIL":
            overall = "FAIL"
        elif status == "WARNING" and overall != "FAIL":
            overall = "WARNING"

    passed   = len([c for c in checks if c["status"] == "PASS"])
    warnings = len([c for c in checks if c["status"] == "WARNING"])
    failed   = len([c for c in checks if c["status"] == "FAIL"])

    summary = ("All ingredients are compliant with FSANZ." if overall == "PASS"
               else f"{warnings} item(s) require review." if overall == "WARNING"
               else f"{failed} item(s) are non-compliant with FSANZ.")

    report = {"overall_status": overall, "ingredient_text": ingredient_text, "checks": checks,
              "total_checks": len(checks), "passed": passed, "warnings": warnings, "failed": failed, "summary": summary}

    log_to_s3("compliance-logs/ingredients", {"timestamp": datetime.utcnow().isoformat(), **report})
    return report


# ─────────────────────────────────────────────
# MODULE 2 — LABELLING COMPLIANCE
# ─────────────────────────────────────────────

def run_labelling_compliance(form_data: dict) -> dict:
    """Check product labelling against FSANZ requirements using form data"""
    print("Running labelling compliance check...")

    context = get_fsanz_context(
        "FSANZ labelling requirements nutrition information panel allergen declaration "
        "date marking country of origin warning statements ingredients list"
    )

    prompt = f"""You are a FSANZ labelling compliance expert for Australia and New Zealand.

Check whether this food product label meets all FSANZ labelling requirements.

FSANZ LABELLING CONTEXT:
{context}

PRODUCT LABEL DETAILS:
- Product Name: {form_data.get('product_name', 'Not provided')}
- Product Category: {form_data.get('product_category', 'Not provided')}
- Has Ingredients List: {form_data.get('has_ingredients_list', 'No')}
- Has Nutrition Information Panel (NIP): {form_data.get('has_nip', 'No')}
- Has Date Marking (Best Before / Use By): {form_data.get('has_date_marking', 'No')}
- Has Country of Origin: {form_data.get('has_country_of_origin', 'No')}
- Has Allergen Declarations: {form_data.get('has_allergen_declaration', 'No')}
- Allergens Present: {form_data.get('allergens', 'None specified')}
- Has Warning Statements: {form_data.get('has_warning_statements', 'No')}
- Additional Notes: {form_data.get('additional_notes', 'None')}

Check each labelling requirement and return a JSON array. Raw JSON only — no markdown.
[
  {{
    "requirement": "requirement name",
    "status": "PASS or WARNING or FAIL",
    "message": "one sentence explanation",
    "standard": "Standard X.X.X",
    "recommendation": "what to do if not compliant"
  }}
]

Check these requirements:
1. Ingredients list present and correctly formatted
2. Nutrition Information Panel (NIP) present
3. Date marking (best before or use by) present
4. Country of origin labelling present
5. Allergen declarations correct and complete
6. Warning statements where required
7. Product name and description accurate"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    print(f"[labelling] Response: {raw[:300]}")

    try:
        checks  = extract_json(raw)
        if isinstance(checks, dict):
            checks = [checks]
    except:
        checks = [{"requirement": "Labelling Check", "status": "WARNING",
                   "message": "Could not complete labelling check. Manual review recommended.",
                   "standard": "FSANZ Food Standards Code", "recommendation": "Consult FSANZ labelling requirements."}]

    overall  = "PASS"
    for c in checks:
        s = c.get("status", "WARNING").upper()
        c["status"] = s
        if s == "FAIL":
            overall = "FAIL"
        elif s == "WARNING" and overall != "FAIL":
            overall = "WARNING"

    passed   = len([c for c in checks if c["status"] == "PASS"])
    warnings = len([c for c in checks if c["status"] == "WARNING"])
    failed   = len([c for c in checks if c["status"] == "FAIL"])

    summary = ("All labelling requirements are met." if overall == "PASS"
               else f"{warnings} labelling requirement(s) need attention." if overall == "WARNING"
               else f"{failed} labelling requirement(s) are not met.")

    report = {"overall_status": overall, "product_name": form_data.get("product_name", ""),
              "checks": checks, "total_checks": len(checks), "passed": passed,
              "warnings": warnings, "failed": failed, "summary": summary}

    log_to_s3("compliance-logs/labelling", {"timestamp": datetime.utcnow().isoformat(), **report})
    return report


# ─────────────────────────────────────────────
# MODULE 3 — COMBINED COMPLIANCE
# ─────────────────────────────────────────────

def run_combined_compliance(ingredient_text: str, form_data: dict, image_bytes: bytes = None, media_type: str = None) -> dict:
    """Run both ingredients and labelling compliance together"""
    print("Running combined compliance check...")

    ingredients_report = run_ingredients_compliance(ingredient_text, image_bytes, media_type)
    labelling_report   = run_labelling_compliance(form_data)

    # Overall combined status
    statuses = [ingredients_report["overall_status"], labelling_report["overall_status"]]
    if "FAIL" in statuses:
        combined_overall = "FAIL"
    elif "WARNING" in statuses:
        combined_overall = "WARNING"
    else:
        combined_overall = "PASS"

    combined_summary = (
        "Both ingredients and labelling are fully compliant with FSANZ." if combined_overall == "PASS"
        else "Some issues found. Please review the ingredient and labelling results below."
        if combined_overall == "WARNING"
        else "Non-compliance found. Reformulation or labelling changes are required."
    )

    report = {
        "overall_status":       combined_overall,
        "summary":              combined_summary,
        "ingredients_report":   ingredients_report,
        "labelling_report":     labelling_report,
        "total_ingredient_checks": ingredients_report["total_checks"],
        "total_labelling_checks":  labelling_report["total_checks"],
        "ingredients_passed":   ingredients_report["passed"],
        "ingredients_warnings": ingredients_report["warnings"],
        "ingredients_failed":   ingredients_report["failed"],
        "labelling_passed":     labelling_report["passed"],
        "labelling_warnings":   labelling_report["warnings"],
        "labelling_failed":     labelling_report["failed"],
    }

    log_to_s3("compliance-logs/combined", {"timestamp": datetime.utcnow().isoformat(), **report})
    return report


# ─────────────────────────────────────────────
# LEGACY — keep old function name working
# ─────────────────────────────────────────────
def run_compliance_check(ingredient_text: str, image_bytes: bytes = None, media_type: str = None) -> dict:
    return run_ingredients_compliance(ingredient_text, image_bytes, media_type)
