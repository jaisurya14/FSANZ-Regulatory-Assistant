from fastapi import FastAPI, HTTPException
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

# --- Compliance Checker Endpoint ---
@app.post("/check-compliance")
def check_compliance(request: ComplianceRequest):
    if not request.ingredient_text.strip():
        raise HTTPException(status_code=400, detail="Ingredient text cannot be empty")
    return run_compliance_check(request.ingredient_text)
