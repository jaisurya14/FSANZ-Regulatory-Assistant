import os
import json
from datetime import datetime
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
import anthropic
import boto3

load_dotenv(dotenv_path="../.env")

# Load all models once
print("Loading models...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
pinecone_index = pc.Index("fsanz-index")
claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
s3_client = boto3.client('s3', region_name=os.getenv("AWS_REGION"))
BUCKET = os.getenv("S3_BUCKET")
print("Ready.")

def log_to_s3(question: str, answer: str, pages: list):
    """Save every question and answer to S3 for audit trail"""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "question": question,
        "answer": answer,
        "pages_referenced": pages
    }
    key = f"logs/{datetime.utcnow().strftime('%Y-%m-%d')}/{datetime.utcnow().strftime('%H-%M-%S')}.json"
    s3_client.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(log_entry, indent=2).encode('utf-8'),
        ContentType='application/json'
    )
    print(f"Logged to S3: {key}")

def answer_question(question: str) -> dict:
    # Step 1: Embed question
    question_vector = embedding_model.encode(question).tolist()

    # Step 2: Search Pinecone
    results = pinecone_index.query(
        vector=question_vector,
        top_k=5,
        include_metadata=True
    )

    chunks = [r["metadata"]["text"] for r in results["matches"]]
    pages  = [r["metadata"]["page"] for r in results["matches"]]
    context = "\n\n---\n\n".join(chunks)

    # Step 3: Ask Claude
    prompt = f"""You are an expert regulatory affairs assistant specialising in the FSANZ Food Standards Code for Australia and New Zealand.

Your job is to answer food regulatory questions clearly and professionally for food product developers.

Use the FSANZ excerpts below as your PRIMARY source. You may also use your knowledge of the FSANZ Food Standards Code to supplement the answer if the excerpts do not fully cover the question — but always make it clear what comes from the excerpts vs your general knowledge.

FSANZ CODE EXCERPTS:
{context}

QUESTION: {question}

Structure your answer as follows:
**1. Direct Answer**
Give a clear, direct answer to the question.

**2. Relevant Standard Reference**
Cite the specific Standard number (e.g. Standard 1.2.3) and schedule if applicable.

**3. Page / Source Reference**
Reference the page number from the excerpts or note if from general FSANZ knowledge.

**4. Conditions or Exceptions**
List any conditions, maximum levels, exceptions, or additional requirements.

Be concise, professional, and accurate. If genuinely unsure, say so clearly.
"""

    response = claude_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    answer = response.content[0].text

    # Step 4: Log to S3
    log_to_s3(question, answer, pages)

    return {
        "answer": answer,
        "pages_referenced": pages,
        "source": "FSANZ Food Standards Code, March 2025"
    }
