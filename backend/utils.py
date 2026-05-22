import os
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

import anthropic
import boto3
from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

print("Loading models...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
claude          = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
s3              = boto3.client('s3', region_name=os.getenv("AWS_REGION"))
BUCKET          = os.getenv("S3_BUCKET")
_pc             = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
pinecone_index  = _pc.Index("fsanz-index")
print("Ready.")


def _claude_create(**kwargs):
    for attempt in range(3):
        try:
            return claude.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise


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


def log_to_s3(folder: str, data: dict):
    key = (
        f"{folder}/{datetime.utcnow().strftime('%Y-%m-%d')}/"
        f"{datetime.utcnow().strftime('%H-%M-%S')}-{uuid.uuid4().hex[:8]}.json"
    )
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(data, indent=2).encode('utf-8'),
        ContentType='application/json'
    )
    print(f"Logged to S3: {key}")
