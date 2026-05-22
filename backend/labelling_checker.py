import os
import re
import json
from datetime import datetime
from pathlib import Path
from dotenv import dotenv_values
import anthropic
import boto3
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

_env = dotenv_values(Path(__file__).parent.parent / ".env")
def _get(key: str) -> str:
    return _env.get(key) or os.environ.get(key, "")

claude          = anthropic.Anthropic(api_key=_get("ANTHROPIC_API_KEY"))
s3              = boto3.client('s3', region_name=_get("AWS_REGION"))
BUCKET          = _get("S3_BUCKET")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
pc              = Pinecone(api_key=_get("PINECONE_API_KEY"))
pinecone_index  = pc.Index("fsanz-index")

LABEL_FIELDS = [
    "product_name",
    "business_name_address",
    "ingredient_list",
    "allergen_declaration",
    "nutrition_information",
    "country_of_origin",
    "storage_instructions",
    "net_weight_volume",
    "date_marking",
    "lot_identification",
]

FIELD_LABELS = {
    "product_name":          "Product Name",
    "business_name_address": "Business Name & Address",
    "ingredient_list":       "Ingredient List",
    "allergen_declaration":  "Allergen Declaration",
    "nutrition_information": "Nutrition Information Panel",
    "country_of_origin":     "Country of Origin",
    "storage_instructions":  "Storage Instructions",
    "net_weight_volume":     "Net Weight / Volume",
    "date_marking":          "Date Marking",
    "lot_identification":    "Lot Identification",
}


def extract_json(text: str):
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    raise ValueError(f"Could not extract JSON: {text[:200]}")


def get_labelling_context(label_data: dict) -> str:
    """Fetch FSANZ context relevant to food labelling requirements."""
    query = (
        "FSANZ food labelling requirements product name business address "
        "ingredient list allergen declaration nutrition information panel "
        "country of origin storage instructions net weight date marking lot identification "
        + " ".join(v for v in label_data.values() if v and len(v) < 100)
    )
    vector  = embedding_model.encode(query).tolist()
    results = pinecone_index.query(vector=vector, top_k=10, include_metadata=True)
    return "\n\n---\n\n".join([r["metadata"].get("text", "") for r in results["matches"]])


def check_label_fields(label_data: dict) -> list:
    """Send all 10 label fields to Claude in one call for FSANZ validation."""
    context = get_labelling_context(label_data)

    fields_text = "\n".join([
        f"{i+1}. {FIELD_LABELS[field]}: {label_data.get(field, '').strip() or '[NOT PROVIDED]'}"
        for i, field in enumerate(LABEL_FIELDS)
    ])

    prompt = f"""You are a FSANZ food labelling compliance expert. Evaluate each label field below against the FSANZ Food Standards Code.

FSANZ CONTEXT:
{context}

LABEL FIELDS SUBMITTED:
{fields_text}

For each field, assess whether it is:
- Present: the field has been provided (not blank)
- Complete: the content appears to cover what FSANZ requires
- Correct format: the content follows FSANZ formatting or declaration rules

Return a JSON array — one object per field, in the same order as above. Raw JSON only, no markdown.

[
  {{
    "field": "product_name",
    "label": "Product Name",
    "status": "PASS",
    "message": "One sentence on why this passes, warns, or fails.",
    "standard": "Standard X.X.X or Schedule X",
    "recommendation": "Specific fix required (empty string if PASS)"
  }}
]

Status rules:
- PASS: present, appears complete and correctly formatted
- WARNING: present but incomplete, ambiguous, or may need review
- FAIL: missing entirely or clearly non-compliant

Fields to check (in order): product_name, business_name_address, ingredient_list, allergen_declaration, nutrition_information, country_of_origin, storage_instructions, net_weight_volume, date_marking, lot_identification"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    print(f"[check_label_fields] Raw response: {raw[:500]}")

    try:
        result = extract_json(raw)
        if isinstance(result, dict):
            result = [result]
        return result
    except Exception as e:
        print(f"[check_label_fields] Parse error: {e}")
        return _fallback_checks(label_data)


def _fallback_checks(label_data: dict) -> list:
    """Simple presence-based fallback if Claude JSON parse fails."""
    results = []
    for field in LABEL_FIELDS:
        value = label_data.get(field, "").strip()
        if value:
            results.append({
                "field":          field,
                "label":          FIELD_LABELS[field],
                "status":         "WARNING",
                "message":        "Provided but could not be fully validated. Manual review recommended.",
                "standard":       "FSANZ Food Standards Code",
                "recommendation": "Please verify against the FSANZ Food Standards Code."
            })
        else:
            results.append({
                "field":          field,
                "label":          FIELD_LABELS[field],
                "status":         "FAIL",
                "message":        "Field not provided.",
                "standard":       "FSANZ Food Standards Code",
                "recommendation": f"Add the {FIELD_LABELS[field]} to your label."
            })
    return results


def build_next_steps(checks: list) -> list:
    """Extract ordered recommended next steps from WARNING and FAIL items."""
    steps = []
    for check in checks:
        if check["status"] in ("WARNING", "FAIL") and check.get("recommendation"):
            steps.append(check["recommendation"])
    return steps


def log_labelling_report_to_s3(label_data: dict, report: dict):
    log = {
        "timestamp":      datetime.utcnow().isoformat(),
        "label_data":     label_data,
        "overall_status": report["overall_status"],
        "checks":         report["checks"],
        "next_steps":     report["next_steps"],
    }
    key = f"labelling-logs/{datetime.utcnow().strftime('%Y-%m-%d')}/{datetime.utcnow().strftime('%H-%M-%S')}.json"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(log, indent=2).encode("utf-8"),
        ContentType="application/json"
    )
    print(f"Labelling report logged to S3: {key}")


def generate_label_html(label_data: dict) -> str:
    """Use Claude to generate a styled, print-ready HTML food label from the 10 label fields."""

    fields_text = "\n".join([
        f"{FIELD_LABELS[field]}: {label_data.get(field, '').strip() or '[Not provided]'}"
        for field in LABEL_FIELDS
    ])

    prompt = f"""You are an Australian food label designer. Generate a complete, self-contained HTML food label that looks like a real product label compliant with the FSANZ Food Standards Code.

LABEL FIELDS PROVIDED:
{fields_text}

STRICT RULES — READ CAREFULLY:
- Use ONLY the exact text provided in the label fields above. Do NOT invent, add, or guess any content.
- Do NOT add taglines, slogans, subtitles, or marketing phrases that are not in the fields provided.
- Do NOT add any extra text under the product name — only the net weight/volume goes below it.
- If a field says "[Not provided]", still show the section label but display "No information provided" in italics grey text underneath it.
- Never invent product names, descriptions, or any other content not supplied by the user.

DESIGN REQUIREMENTS:
- Self-contained single HTML file — all CSS must be inside a <style> tag in the <head>
- Clean white label with a solid dark border (simulate a physical label)
- Max width 620px, centred on the page with a light grey page background
- Use Arial or Helvetica font throughout

LAYOUT (top to bottom — follow this exact order):
1. Product name — very large (28-32pt), bold, centred, ALL CAPS, with a thick bottom border. Nothing else on this line.
2. Net weight / volume — below product name, centred, medium size
3. NUTRITION INFORMATION PANEL — formatted as a proper HTML table:
   - Header row: dark background, white text
   - Columns: Nutrient | Per Serve | Per 100g or Per 100mL
   - Rows: Energy (kJ), Protein (g), Fat total (g), — Saturated (g), Carbohydrate (g), — Sugars (g), Dietary Fibre (g), Sodium (mg)
   - Add any vitamins/minerals mentioned in the nutrition_information field
   - Alternating row shading for readability
   - Parse the nutrition_information text to fill in the values; use "—" if a value is not mentioned
4. INGREDIENTS — label "INGREDIENTS:" in bold, then list the ingredients in normal text. Bold any allergens mentioned.
5. ALLERGEN DECLARATION — bold label "ALLERGEN DECLARATION:", content in bold
6. Storage instructions — label in bold, content in normal text
7. Country of origin — in normal text, use the exact wording provided
8. Date marking — "Best Before:" or "Use By:" label in bold
9. Lot identification — small text, "Lot No:" label
10. Business name & address — small text at the very bottom, separated by a top border

STYLING DETAILS:
- Each section separated by a thin horizontal rule or spacing
- Section labels (INGREDIENTS:, etc.) in bold, uppercase, small font
- Allergens must appear in bold wherever they are mentioned
- NIP table must have clear borders and be easy to read
- The overall label must look professional and print-ready
- Add a small footer note at the very bottom: "This is a draft label for review purposes only."

Return ONLY the complete HTML document. No explanation, no markdown, no code fences."""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if Claude wraps in them
    raw = re.sub(r"^```(?:html)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def run_labelling_check(label_data: dict) -> dict:
    """Run full FSANZ labelling compliance check on the 10-field structured input."""
    print("=" * 50)
    print("Running labelling compliance check...")

    checks_raw = check_label_fields(label_data)
    print(f"Got {len(checks_raw)} field checks")

    checks  = []
    overall = "PASS"

    positional_idx = 0
    for field in LABEL_FIELDS:
        # Match result by field key first; fall back to positional with dedicated counter
        match = next(
            (c for c in checks_raw if c.get("field") == field),
            checks_raw[positional_idx] if positional_idx < len(checks_raw) else None
        )
        positional_idx += 1

        if match is None:
            value = label_data.get(field, "").strip()
            match = {
                "field":          field,
                "label":          FIELD_LABELS[field],
                "status":         "FAIL" if not value else "WARNING",
                "message":        "Not provided." if not value else "Could not be validated.",
                "standard":       "FSANZ Food Standards Code",
                "recommendation": f"Add {FIELD_LABELS[field]}." if not value else "",
            }

        status = match.get("status", "WARNING").upper()
        if status not in ("PASS", "WARNING", "FAIL"):
            status = "WARNING"

        checks.append({
            "field":          field,
            "label":          match.get("label", FIELD_LABELS[field]),
            "status":         status,
            "message":        match.get("message", ""),
            "standard":       match.get("standard", ""),
            "recommendation": match.get("recommendation", ""),
        })

        if status == "FAIL":
            overall = "FAIL"
        elif status == "WARNING" and overall != "FAIL":
            overall = "WARNING"

    passed   = sum(1 for c in checks if c["status"] == "PASS")
    warnings = sum(1 for c in checks if c["status"] == "WARNING")
    failed   = sum(1 for c in checks if c["status"] == "FAIL")
    next_steps = build_next_steps(checks)

    if overall == "PASS":
        summary = "All label requirements appear compliant with the FSANZ Food Standards Code."
    elif overall == "WARNING":
        summary = f"{warnings} label field(s) require review before the product can go to market."
    else:
        summary = f"{failed} label field(s) are missing or non-compliant with the FSANZ Food Standards Code."

    report = {
        "overall_status": overall,
        "summary":        summary,
        "checks":         checks,
        "total_checks":   len(checks),
        "passed":         passed,
        "warnings":       warnings,
        "failed":         failed,
        "next_steps":     next_steps,
    }

    try:
        log_labelling_report_to_s3(label_data, report)
    except Exception as e:
        print(f"[log_labelling_report_to_s3] Warning: {e}")
    print(f"Done — {passed} PASS, {warnings} WARNING, {failed} FAIL")
    print("=" * 50)

    return report
