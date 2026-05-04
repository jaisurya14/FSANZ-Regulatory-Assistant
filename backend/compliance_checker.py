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

load_dotenv(dotenv_path="../.env")

claude          = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
s3              = boto3.client('s3', region_name=os.getenv("AWS_REGION"))
BUCKET          = os.getenv("S3_BUCKET")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
pc              = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
pinecone_index  = pc.Index("fsanz-index")


def extract_json(text: str):
    """Robustly extract JSON from Claude response — handles markdown, extra text, etc."""
    # Remove markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except:
        pass

    # Try to find a JSON array inside the text
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass

    # Try to find a JSON object inside the text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass

    raise ValueError(f"Could not extract JSON from response: {text[:200]}")


def extract_ingredients_from_text(ingredient_text: str) -> list:
    """Use Claude to extract ingredients and amounts from plain text"""
    prompt = f"""Extract all ingredients and amounts from this list.
Return ONLY a JSON array. No explanation. No markdown.
Example: [{{"ingredient": "sugar", "amount": "45g/kg"}}, {{"ingredient": "water", "amount": "not specified"}}]
If amount not given, use "not specified".

Ingredient list: {ingredient_text}"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    print(f"[extract_ingredients] Raw response: {raw[:300]}")

    try:
        return extract_json(raw)
    except Exception as e:
        print(f"[extract_ingredients] Parse error: {e}")
        return []


def extract_ingredients_from_image(image_bytes: bytes, media_type: str) -> list:
    """Use Claude Vision to extract ingredients from a food label image"""
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    prompt = """Look at this food product label image and extract ALL ingredients and amounts.
Return ONLY a JSON array. No markdown. No explanation.
Format: [{"ingredient": "sugar", "amount": "45g/kg"}, {"ingredient": "water", "amount": "not specified"}]
If you cannot find ingredients, return: []"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                {"type": "text", "text": prompt}
            ]
        }]
    )

    raw = response.content[0].text
    print(f"[extract_from_image] Raw response: {raw[:300]}")

    try:
        return extract_json(raw)
    except Exception as e:
        print(f"[extract_from_image] Parse error: {e}")
        return []


def get_fsanz_context(ingredients: list) -> str:
    """Single Pinecone search covering all ingredients"""
    combined = "FSANZ permitted levels additives preservatives allergens colours " + \
               " ".join([item["ingredient"] for item in ingredients])
    vector  = embedding_model.encode(combined).tolist()
    results = pinecone_index.query(vector=vector, top_k=8, include_metadata=True)
    return "\n\n---\n\n".join([r["metadata"]["text"] for r in results["matches"]])


def check_all_ingredients(ingredients: list) -> list:
    """Check ALL ingredients in ONE Claude call"""
    context = get_fsanz_context(ingredients)

    numbered = "\n".join([
        f"{i+1}. {item['ingredient']} — amount: {item['amount']}"
        for i, item in enumerate(ingredients)
    ])

    prompt = f"""You are a FSANZ compliance expert. Check each ingredient below against FSANZ rules.

FSANZ CONTEXT:
{context}

INGREDIENTS:
{numbered}

Return a JSON array with one object per ingredient. Raw JSON only — no markdown, no explanation.

[
  {{
    "ingredient": "name",
    "status": "PASS",
    "message": "one sentence",
    "standard": "Standard X.X.X or Schedule X",
    "recommendation": ""
  }}
]

Status rules:
- PASS: within limits or no restrictions
- WARNING: allergen needs declaration, near limit, or uncertain
- FAIL: exceeds permitted level or not permitted"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    print(f"[check_all] Raw response: {raw[:500]}")

    try:
        result = extract_json(raw)
        # If Claude returned a single dict instead of list, wrap it
        if isinstance(result, dict):
            result = [result]
        return result
    except Exception as e:
        print(f"[check_all] Parse error: {e}")
        # Fallback — ask Claude again with a simpler prompt
        return check_all_ingredients_simple(ingredients)


def check_all_ingredients_simple(ingredients: list) -> list:
    """Simplified fallback check — one ingredient at a time if batch fails"""
    results = []
    for item in ingredients:
        prompt = f"""Is {item['ingredient']} (amount: {item['amount']}) compliant with FSANZ Food Standards Code?
Return only this JSON, no markdown:
{{"ingredient": "{item['ingredient']}", "status": "PASS", "message": "brief reason", "standard": "Standard reference", "recommendation": ""}}
Use PASS, WARNING, or FAIL for status."""

        try:
            response = claude.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text
            print(f"[simple_check] {item['ingredient']}: {raw[:150]}")
            verdict = extract_json(raw)
            if isinstance(verdict, list):
                verdict = verdict[0]
            results.append(verdict)
        except Exception as e:
            print(f"[simple_check] Error for {item['ingredient']}: {e}")
            results.append({
                "ingredient":     item["ingredient"],
                "status":         "WARNING",
                "message":        "Could not determine compliance. Manual review recommended.",
                "standard":       "FSANZ Food Standards Code",
                "recommendation": "Please consult the full FSANZ Food Standards Code."
            })
    return results


def log_compliance_to_s3(ingredient_text: str, report: dict):
    """Save compliance report to S3"""
    log = {
        "timestamp":       datetime.utcnow().isoformat(),
        "ingredient_text": ingredient_text,
        "overall_status":  report["overall_status"],
        "checks":          report["checks"]
    }
    key = f"compliance-logs/{datetime.utcnow().strftime('%Y-%m-%d')}/{datetime.utcnow().strftime('%H-%M-%S')}.json"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(log, indent=2).encode('utf-8'),
        ContentType='application/json'
    )
    print(f"Compliance report logged to S3: {key}")


def run_compliance_check(ingredient_text: str, image_bytes: bytes = None, media_type: str = None) -> dict:
    """Run full FSANZ compliance check — accepts text or image"""
    print("=" * 50)
    print("Running compliance check...")

    # Step 1: Extract ingredients
    if image_bytes:
        print("Mode: image upload")
        ingredients = extract_ingredients_from_image(image_bytes, media_type)
    else:
        print("Mode: text input")
        ingredients = extract_ingredients_from_text(ingredient_text)

    print(f"Extracted {len(ingredients)} ingredients: {[i['ingredient'] for i in ingredients]}")

    if not ingredients:
        return {
            "overall_status": "ERROR",
            "ingredient_text": ingredient_text,
            "checks":          [],
            "total_checks":    0,
            "passed":          0,
            "warnings":        0,
            "failed":          0,
            "summary":         "Could not extract ingredients. Please check your input."
        }

    # Step 2: Check all ingredients
    verdicts = check_all_ingredients(ingredients)
    print(f"Got {len(verdicts)} verdicts")

    # Step 3: Build checks list
    checks  = []
    overall = "PASS"

    for i, item in enumerate(ingredients):
        if i < len(verdicts):
            verdict = verdicts[i]
        else:
            verdict = {"status": "WARNING", "message": "Not checked.", "standard": "", "recommendation": ""}

        status = verdict.get("status", "WARNING").upper()
        if status not in ["PASS", "WARNING", "FAIL"]:
            status = "WARNING"

        checks.append({
            "ingredient":     item["ingredient"],
            "amount":         item.get("amount", "not specified"),
            "status":         status,
            "message":        verdict.get("message", ""),
            "standard":       verdict.get("standard", ""),
            "recommendation": verdict.get("recommendation", "")
        })

        if status == "FAIL":
            overall = "FAIL"
        elif status == "WARNING" and overall != "FAIL":
            overall = "WARNING"

    # Step 4: Counts and summary
    passed   = len([c for c in checks if c["status"] == "PASS"])
    warnings = len([c for c in checks if c["status"] == "WARNING"])
    failed   = len([c for c in checks if c["status"] == "FAIL"])

    if overall == "PASS":
        summary = "All ingredients are compliant with the FSANZ Food Standards Code."
    elif overall == "WARNING":
        summary = f"{warnings} item(s) require review or additional labelling."
    else:
        summary = f"{failed} item(s) are non-compliant with the FSANZ Food Standards Code."

    report = {
        "overall_status":  overall,
        "ingredient_text": ingredient_text,
        "checks":          checks,
        "total_checks":    len(checks),
        "passed":          passed,
        "warnings":        warnings,
        "failed":          failed,
        "summary":         summary
    }

    log_compliance_to_s3(ingredient_text, report)
    print(f"Done — {passed} PASS, {warnings} WARNING, {failed} FAIL")
    print("=" * 50)

    return report
