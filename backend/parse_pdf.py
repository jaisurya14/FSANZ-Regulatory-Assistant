import fitz
import json
import os
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from aws_helper import download_file_from_s3, upload_json_to_s3

load_dotenv(dotenv_path="../.env")

def parse_fsanz_pdf():
    # Step 1: Download PDF from S3
    local_pdf = "../data/raw/food_standards_code.pdf"
    download_file_from_s3(
        s3_key="raw/food_standards_code.pdf",
        local_path=local_pdf
    )

    # Step 2: Open and parse PDF
    print("Parsing PDF...")
    doc = fitz.open(local_pdf)
    print(f"Total pages: {len(doc)}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", ". "]
    )

    all_chunks = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        if not text.strip():
            continue
        page_chunks = splitter.split_text(text)
        for chunk in page_chunks:
            all_chunks.append({
                "text": chunk,
                "page": page_num + 1,
                "source": "FSANZ Food Standards Code March 2025"
            })
        if page_num % 100 == 0:
            print(f"Processed page {page_num}/{len(doc)}")

    print(f"Total chunks created: {len(all_chunks)}")

    # Step 3: Save locally
    os.makedirs("../data/processed", exist_ok=True)
    local_chunks = "../data/processed/chunks.json"
    with open(local_chunks, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    # Step 4: Upload chunks to S3
    upload_json_to_s3(
        data=all_chunks,
        s3_key="processed/chunks.json"
    )

    print("Done! Chunks saved locally and uploaded to S3.")
    return all_chunks

if __name__ == "__main__":
    parse_fsanz_pdf()
