import os
import json
from datetime import datetime
from dotenv import load_dotenv
import anthropic
import boto3
from rag_pipeline import answer_question

load_dotenv(dotenv_path="../.env")

claude  = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
s3      = boto3.client('s3', region_name=os.getenv("AWS_REGION"))
BUCKET  = os.getenv("S3_BUCKET")


def extract_ingredients(ingredient_text: str) -> list:
    """Use Claude to extract all ingredients and amounts from ingredient list"""
    prompt = f"""You are a food science expert. Extract all ingredients and their amounts from this ingredient list.
Return as a JSON list ONLY. No explanation. No extra text.
Format: [{{"ingredient": "sugar", "amount": "45g/kg"}}, {{"ingredient": "apple juice", "amount": "30%"}}]
If no amount is given for an ingredient write "not specified" for the amount.

Ingredient list: {ingredient_text}"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        return json.loads(response.content[0].text)
    except:
        return []


def check_single_ingredient(ingredient: str, amount: str) -> dict:
    """Check one ingredient against FSANZ rules using RAG pipeline"""
    question = f"What is the maximum permitted level and conditions for {ingredient} in juice beverages or food products under FSANZ Food Standards Code?"
    result   = answer_question(question)

    verdict_prompt = f"""You are a FSANZ compliance expert.

Based on this FSANZ regulatory information:
{result['answer']}

Determine if the following is compliant:
Ingredient: {ingredient}
Amount used: {amount}

Return ONLY a JSON object in this exact format:
{{
  "status": "PASS or WARNING or FAIL",
  "message": "one sentence explanation",
  "standard": "e.g. Standard 2.6.1 or Schedule 15",
  "recommendation": "what to do if not compliant, or empty string if compliant"
}}

Rules:
- PASS = clearly within limits or no restrictions found
- WARNING = close to limit, unclear, or needs label declaration
- FAIL = clearly exceeds limit or not permitted"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": verdict_prompt}]
    )

    try:
        return json.loads(response.content[0].text)
    except:
        return {
            "status": "WARNING",
            "message": "Could not determine compliance. Manual review recommended.",
            "standard": "FSANZ Food Standards Code",
            "recommendation": "Please consult the full FSANZ Food Standards Code."
        }


def log_compliance_to_s3(ingredient_text: str, report: dict):
    """Save compliance check report to S3"""
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


def run_compliance_check(ingredient_text: str) -> dict:
    """Run full FSANZ compliance check on an ingredient list"""
    print(f"Running compliance check...")

    # Step 1: Extract all ingredients
    ingredients = extract_ingredients(ingredient_text)
    print(f"Extracted {len(ingredients)} ingredients")

    if not ingredients:
        return {
            "overall_status": "ERROR",
            "ingredient_text": ingredient_text,
            "checks": [],
            "total_checks": 0,
            "passed": 0,
            "warnings": 0,
            "failed": 0,
            "summary": "Could not extract ingredients. Please check your input format."
        }

    # Step 2: Check each ingredient
    checks  = []
    overall = "PASS"

    for item in ingredients:
        print(f"Checking: {item['ingredient']} ({item['amount']})")
        result = check_single_ingredient(item["ingredient"], item["amount"])

        checks.append({
            "ingredient":     item["ingredient"],
            "amount":         item.get("amount", "not specified"),
            "status":         result.get("status", "WARNING"),
            "message":        result.get("message", ""),
            "standard":       result.get("standard", ""),
            "recommendation": result.get("recommendation", "")
        })

        if result.get("status") == "FAIL":
            overall = "FAIL"
        elif result.get("status") == "WARNING" and overall != "FAIL":
            overall = "WARNING"

    # Step 3: Build summary
    passed   = len([c for c in checks if c["status"] == "PASS"])
    warnings = len([c for c in checks if c["status"] == "WARNING"])
    failed   = len([c for c in checks if c["status"] == "FAIL"])

    if overall == "PASS":
        summary = "All ingredients checked are compliant with the FSANZ Food Standards Code."
    elif overall == "WARNING":
        summary = f"{warnings} item(s) require review or additional labelling. Please check warnings carefully."
    else:
        summary = f"{failed} item(s) are non-compliant with the FSANZ Food Standards Code. Reformulation or labelling changes required."

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

    # Step 4: Log to S3
    log_compliance_to_s3(ingredient_text, report)

    return report
