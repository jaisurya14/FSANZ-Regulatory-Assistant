import os
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from aws_helper import download_json_from_s3

load_dotenv(dotenv_path="../.env")

def index_to_pinecone():
    # Step 1: Download chunks from S3
    chunks = download_json_from_s3(s3_key="processed/chunks.json")
    print(f"Loaded {len(chunks)} chunks from S3")

    # Step 2: Load embedding model
    print("Loading embedding model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')

    # Step 3: Connect to Pinecone
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index("fsanz-index")

    # Step 4: Upload in batches
    batch_size = 100
    total_batches = (len(chunks) // batch_size) + 1

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c["text"] for c in batch]
        embeddings = model.encode(texts).tolist()

        vectors = []
        for j, chunk in enumerate(batch):
            vectors.append({
                "id": f"chunk-{i+j}",
                "values": embeddings[j],
                "metadata": {
                    "text": chunk["text"],
                    "page": chunk["page"],
                    "source": chunk["source"]
                }
            })

        index.upsert(vectors=vectors)
        print(f"Batch {i//batch_size + 1}/{total_batches} uploaded to Pinecone")

    print("All chunks indexed in Pinecone!")

if __name__ == "__main__":
    index_to_pinecone()
