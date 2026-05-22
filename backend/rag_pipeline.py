from datetime import datetime
from utils import embedding_model, pinecone_index, _claude_create, log_to_s3


def answer_question(question: str) -> dict:
    question_vector = embedding_model.encode(question).tolist()

    results = pinecone_index.query(
        vector=question_vector,
        top_k=5,
        include_metadata=True
    )

    chunks = [r["metadata"].get("text", "") for r in results["matches"] if r.get("metadata")]
    pages  = [r["metadata"].get("page", r["metadata"].get("source", "unknown")) for r in results["matches"] if r.get("metadata")]
    context = "\n\n---\n\n".join(chunks)

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

    response = _claude_create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )

    if not response.content or not hasattr(response.content[0], "text"):
        raise ValueError("No text response received from Claude.")
    answer = response.content[0].text

    try:
        log_to_s3("logs", {
            "timestamp":       datetime.utcnow().isoformat(),
            "question":        question,
            "answer":          answer,
            "pages_referenced": pages,
        })
    except Exception as e:
        print(f"[log_to_s3] Warning: {e}")

    return {
        "answer":           answer,
        "pages_referenced": pages,
        "source":           "FSANZ Food Standards Code, March 2025",
    }
