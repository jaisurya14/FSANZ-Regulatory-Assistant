from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rag_pipeline import answer_question
from compliance_checker import run_compliance_check

app = FastAPI(title="FSANZ Regulatory Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request Models ---
class QuestionRequest(BaseModel):
    question: str

class ComplianceRequest(BaseModel):
    ingredient_text: str

# --- Health Check ---
@app.get("/health")
def health():
    return {"status": "running"}

# --- Chat Endpoint ---
@app.post("/ask")
def ask(request: QuestionRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    return answer_question(request.question)

# --- Compliance Checker — Text Input ---
@app.post("/check-compliance")
def check_compliance(request: ComplianceRequest):
    if not request.ingredient_text.strip():
        raise HTTPException(status_code=400, detail="Ingredient text cannot be empty")
    return run_compliance_check(ingredient_text=request.ingredient_text)

# --- Compliance Checker — Image Upload ---
@app.post("/check-compliance-image")
async def check_compliance_image(file: UploadFile = File(...)):
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WEBP or GIF images are supported.")
    image_bytes = await file.read()
    return run_compliance_check(
        ingredient_text="Uploaded from image",
        image_bytes=image_bytes,
        media_type=file.content_type
    )
