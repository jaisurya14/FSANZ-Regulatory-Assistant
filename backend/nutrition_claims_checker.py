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


def get_claims_context() -> str:
    """Fetch FSANZ context relevant to nutrition claims."""
    query = (
        "FSANZ nutrition content claims Standard 1.2.7 Schedule 4 "
        "high in low in good source no added sugar reduced fat "
        "permitted nutrition claims thresholds conditions requirements"
    )
    vector  = embedding_model.encode(query).tolist()
    results = pinecone_index.query(vector=vector, top_k=10, include_metadata=True)
    return "\n\n---\n\n".join([r["metadata"].get("text", "") for r in results["matches"]])


def validate_claims(product_name: str, product_type: str, nip_text: str, selected_claims: list) -> list:
    """Extract NIP values and validate all selected claims in one Claude call."""
    context = get_claims_context()

    claims_list = "\n".join([f"- {c}" for c in selected_claims])

    prompt = f"""You are a FSANZ nutrition claims compliance expert.

A food business wants to make the following claims on their label. Your job is to:
1. Read the Nutrition Information Panel (NIP) text they pasted
2. Extract the relevant values for each claim
3. Check each claim against FSANZ Standard 1.2.7 and Schedule 4
4. Return whether they QUALIFY for each claim

FSANZ CONTEXT:
{context}

PRODUCT NAME: {product_name}
PRODUCT TYPE: {product_type}

NUTRITION INFORMATION PANEL (pasted by user):
{nip_text}

CLAIMS TO VALIDATE:
{claims_list}

For each claim, find the relevant nutrient value from the NIP text above and check it against the FSANZ threshold.

RULES — FOLLOW EXACTLY:

1. Output exactly ONE object per claim — no duplicates, no retries, no corrections mid-output.
2. The "message" field must be ONE clean professional sentence only — no arithmetic working, no "re-checking", no internal reasoning. Just the final conclusion.
3. Status must be consistent with the message:
   - Value meets the threshold → "APPROVED"
   - Value does not meet the threshold or exceeds the limit → "REJECTED"
   - Cannot be confirmed from NIP alone (comparative claims, no reference food) → "WARNING"
4. If a nutrient is not declared in the NIP → "REJECTED" (claim cannot be made without a declared value)
5. Comparative claims (Reduced Fat, Light/Lite) with no reference food provided → "WARNING"

Return a JSON array — exactly one object per claim, in the same order as the list above. Raw JSON only, no markdown, no explanations outside the JSON.

[
  {{
    "claim": "High in Vitamin C",
    "status": "APPROVED",
    "user_value": "45mg per 100mL",
    "fsanz_threshold": "At least 25mg per 100mL",
    "message": "One clean professional sentence stating the result.",
    "recommendation": "Specific actionable advice if WARNING or REJECTED, empty string if APPROVED",
    "standard": "Standard 1.2.7, Schedule 4"
  }}
]

Status definitions:
- APPROVED: nutrient is declared in NIP and the value clearly meets the FSANZ threshold
- WARNING: claim is conditional, comparative, or cannot be fully confirmed from the NIP alone
- REJECTED: value does not meet the threshold, exceeds the limit, or nutrient is not declared in the NIP"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    print(f"[validate_claims] Raw: {raw[:400]}")

    try:
        result = extract_json(raw)
        if isinstance(result, dict):
            result = [result]
        return result
    except Exception as e:
        print(f"[validate_claims] Parse error: {e}")
        return [{
            "claim":           c,
            "status":          "WARNING",
            "user_value":      "Could not extract from NIP",
            "fsanz_threshold": "Could not be determined",
            "message":         "Could not validate. Manual review recommended.",
            "recommendation":  "Please check Standard 1.2.7 and Schedule 4 manually.",
            "standard":        "Standard 1.2.7, Schedule 4"
        } for c in selected_claims]


def log_claims_report_to_s3(product_name: str, report: dict):
    log = {
        "timestamp":    datetime.utcnow().isoformat(),
        "product_name": product_name,
        "overall":      report["overall_status"],
        "results":      report["results"],
    }
    key = f"nutrition-claims-logs/{datetime.utcnow().strftime('%Y-%m-%d')}/{datetime.utcnow().strftime('%H-%M-%S')}.json"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(log, indent=2).encode("utf-8"),
        ContentType="application/json"
    )


def run_nutrition_claims_check(product_name: str, product_type: str, nip_text: str, selected_claims: list) -> dict:
    """Validate nutrition claims by reading the pasted NIP text."""
    print("=" * 50)
    print(f"Running nutrition claims check for: {product_name}")

    raw_results = validate_claims(product_name, product_type, nip_text, selected_claims)

    results  = []
    approved = 0
    warnings = 0
    rejected = 0

    for i, claim in enumerate(selected_claims):
        # Match by claim name first (case-insensitive), fall back to positional
        match = next(
            (r for r in raw_results if r.get("claim", "").strip().lower() == claim.strip().lower()),
            raw_results[i] if i < len(raw_results) else None
        )
        if match is None:
            match = {
                "claim":           claim,
                "status":          "WARNING",
                "user_value":      "Not found in NIP",
                "fsanz_threshold": "Unknown",
                "message":         "Could not be validated.",
                "recommendation":  "Manual review recommended.",
                "standard":        "Standard 1.2.7"
            }

        status = match.get("status", "WARNING").upper()
        if status not in ("APPROVED", "WARNING", "REJECTED"):
            status = "WARNING"

        results.append({
            "claim":           match.get("claim", claim),
            "status":          status,
            "user_value":      match.get("user_value", ""),
            "fsanz_threshold": match.get("fsanz_threshold", ""),
            "message":         match.get("message", ""),
            "recommendation":  match.get("recommendation", ""),
            "standard":        match.get("standard", "Standard 1.2.7, Schedule 4"),
        })

        if status == "APPROVED":
            approved += 1
        elif status == "WARNING":
            warnings += 1
        else:
            rejected += 1

    if rejected == 0 and warnings == 0:
        overall_status  = "COMPLIANT"
        overall_message = "All claims are approved and compliant with FSANZ Standard 1.2.7."
    elif rejected == 0:
        overall_status  = "MOSTLY COMPLIANT"
        overall_message = f"{warnings} claim(s) need review before use on label."
    else:
        overall_status  = "NON-COMPLIANT"
        overall_message = f"{rejected} claim(s) do not qualify under FSANZ rules."

    report = {
        "product_name":    product_name,
        "overall_status":  overall_status,
        "overall_message": overall_message,
        "results":         results,
        "total_claims":    len(results),
        "approved":        approved,
        "warnings":        warnings,
        "rejected":        rejected,
    }

    try:
        log_claims_report_to_s3(product_name, report)
    except Exception as e:
        print(f"[log_claims_report_to_s3] Warning: {e}")

    print(f"Done — {approved} APPROVED, {warnings} WARNING, {rejected} REJECTED")
    print("=" * 50)
    return report
