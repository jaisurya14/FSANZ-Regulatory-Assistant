from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import anthropic
from rag_pipeline import answer_question
from compliance_checker import (
    run_ingredients_compliance,
    run_labelling_compliance,
    run_combined_compliance
)
from labelling_checker import run_labelling_check, generate_label_html
from nutrition_claims_checker import run_nutrition_claims_check

def _handle_overload(e: Exception):
    """Return a 503 with a friendly message instead of crashing on API overload."""
    if isinstance(e, anthropic.APIStatusError) and e.status_code == 529:
        return JSONResponse(
            status_code=503,
            content={"detail": "The AI service is temporarily overloaded. Please wait 30 seconds and try again."}
        )
    raise e

app = FastAPI(title="FSANZ Regulatory Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request Models ──────────────────────────────────────────

class QuestionRequest(BaseModel):
    question: str

class IngredientsRequest(BaseModel):
    ingredient_text: str

class LabellingRequest(BaseModel):
    product_name:           str
    product_category:       str
    has_ingredients_list:   str
    has_nip:                str
    has_date_marking:       str
    has_country_of_origin:  str
    has_allergen_declaration: str
    allergens:              Optional[str] = ""
    has_warning_statements: str
    additional_notes:       Optional[str] = ""

# ── Label Checker (10-field structured) ─────────────────────
class LabelCheckRequest(BaseModel):
    product_name:          str = ""
    business_name_address: str = ""
    ingredient_list:       str = ""
    allergen_declaration:  str = ""
    nutrition_information: str = ""
    country_of_origin:     str = ""
    storage_instructions:  str = ""
    net_weight_volume:     str = ""
    date_marking:          str = ""
    lot_identification:    str = ""

# ── Nutrition Claims ─────────────────────────────────────────
class NutritionClaimsRequest(BaseModel):
    product_name:    str = ""
    product_type:    str = ""
    nip_text:        str
    selected_claims: List[str]

class CombinedRequest(BaseModel):
    ingredient_text:        str
    product_name:           str
    product_category:       str
    has_ingredients_list:   str
    has_nip:                str
    has_date_marking:       str
    has_country_of_origin:  str
    has_allergen_declaration: str
    allergens:              Optional[str] = ""
    has_warning_statements: str
    additional_notes:       Optional[str] = ""

# ── Health Check ────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "running"}

# ── Chat ────────────────────────────────────────────────────

@app.post("/ask")
def ask(request: QuestionRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    try:
        return answer_question(request.question)
    except Exception as e:
        return _handle_overload(e)

# ── Module 1: Ingredients Compliance (text) ─────────────────

@app.post("/check-compliance")
def check_compliance(request: IngredientsRequest):
    if not request.ingredient_text.strip():
        raise HTTPException(status_code=400, detail="Ingredient text cannot be empty")
    try:
        return run_ingredients_compliance(ingredient_text=request.ingredient_text)
    except Exception as e:
        return _handle_overload(e)

# ── Module 1: Ingredients Compliance (image) ────────────────

@app.post("/check-compliance-image")
async def check_compliance_image(file: UploadFile = File(...)):
    allowed = ["image/jpeg", "image/png", "image/webp", "image/gif"]
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WEBP or GIF supported.")
    image_bytes = await file.read()
    try:
        return run_ingredients_compliance(
            ingredient_text="Uploaded from image",
            image_bytes=image_bytes,
            media_type=file.content_type
        )
    except Exception as e:
        return _handle_overload(e)

# ── Module 2: Labelling Compliance (form) ───────────────────

@app.post("/check-labelling")
def check_labelling(request: LabellingRequest):
    form_data = request.model_dump()
    try:
        return run_labelling_compliance(form_data)
    except Exception as e:
        return _handle_overload(e)

# ── Module: Label Compliance (10 structured fields) ─────────

@app.post("/check-label")
def check_label(request: LabelCheckRequest):
    label_data = request.model_dump()
    if not any(v.strip() for v in label_data.values()):
        raise HTTPException(status_code=400, detail="At least one label field must be provided.")
    try:
        return run_labelling_check(label_data)
    except Exception as e:
        return _handle_overload(e)

# ── Module: Generate Label HTML ──────────────────────────────

@app.post("/generate-label")
def generate_label(request: LabelCheckRequest):
    label_data = request.model_dump()
    if not any(v.strip() for v in label_data.values()):
        raise HTTPException(status_code=400, detail="At least one label field must be provided.")
    try:
        html = generate_label_html(label_data)
        return {"html": html}
    except Exception as e:
        return _handle_overload(e)

# ── Module: Nutrition Claims Validator ───────────────────────

@app.post("/check-nutrition-claims")
def check_nutrition_claims(request: NutritionClaimsRequest):
    if not request.nip_text.strip():
        raise HTTPException(status_code=400, detail="NIP text cannot be empty.")
    if not request.selected_claims:
        raise HTTPException(status_code=400, detail="At least one claim must be selected.")
    try:
        return run_nutrition_claims_check(
            product_name=request.product_name,
            product_type=request.product_type,
            nip_text=request.nip_text,
            selected_claims=request.selected_claims
        )
    except Exception as e:
        return _handle_overload(e)

# ── Module 3: Combined Compliance (text + form) ─────────────

@app.post("/check-combined")
def check_combined(request: CombinedRequest):
    form_data = request.model_dump()
    ingredient_text = form_data.pop("ingredient_text")
    try:
        return run_combined_compliance(ingredient_text=ingredient_text, form_data=form_data)
    except Exception as e:
        return _handle_overload(e)

# ── Module 3: Combined Compliance (image + form) ────────────

@app.post("/check-combined-image")
async def check_combined_image(
    file:                    UploadFile = File(...),
    product_name:            str = Form(...),
    product_category:        str = Form(...),
    has_ingredients_list:    str = Form(...),
    has_nip:                 str = Form(...),
    has_date_marking:        str = Form(...),
    has_country_of_origin:   str = Form(...),
    has_allergen_declaration: str = Form(...),
    allergens:               str = Form(""),
    has_warning_statements:  str = Form(...),
    additional_notes:        str = Form("")
):
    allowed = ["image/jpeg", "image/png", "image/webp", "image/gif"]
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WEBP or GIF supported.")
    image_bytes = await file.read()
    form_data = {
        "product_name": product_name, "product_category": product_category,
        "has_ingredients_list": has_ingredients_list, "has_nip": has_nip,
        "has_date_marking": has_date_marking, "has_country_of_origin": has_country_of_origin,
        "has_allergen_declaration": has_allergen_declaration, "allergens": allergens,
        "has_warning_statements": has_warning_statements, "additional_notes": additional_notes
    }
    return run_combined_compliance(
        ingredient_text="Uploaded from image",
        form_data=form_data,
        image_bytes=image_bytes,
        media_type=file.content_type
    )
