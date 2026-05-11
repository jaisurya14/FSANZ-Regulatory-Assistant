"""
FSANZ Website Scraper
Scrapes key FSANZ guidance pages and adds them to the knowledge base
Run this once to extend the dataset beyond the main PDF
"""

import os
import json
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from aws_helper import upload_json_to_s3, download_json_from_s3

load_dotenv(dotenv_path="../.env")

# Key FSANZ pages to scrape
FSANZ_URLS = [
    {
        "url": "https://www.foodstandards.gov.au/consumer/labelling",
        "title": "FSANZ Allergen Labelling Guidance"
    },
    {
        "url": "https://www.foodstandards.gov.au/business/labelling",
        "title": "FSANZ Food Labelling Requirements"
    },
    {
        "url": "https://www.foodstandards.gov.au/consumer/nutrition",
        "title": "FSANZ Nutrient Profiling"
    },
    {
        "url": "https://www.foodstandards.gov.au/business/novel-foods",
        "title": "FSANZ Novel Foods"
    },
    {
        "url": "https://www.foodstandards.gov.au/consumer/additives",
        "title": "FSANZ Food Additives"
    },
    {
        "url": "https://www.foodstandards.gov.au/business/labelling/country-of-origin",
        "title": "FSANZ Country of Origin Labelling"
    },
    {
        "url": "https://www.foodstandards.gov.au/consumer/gmfoods",
        "title": "FSANZ Genetically Modified Foods"
    },
    {
        "url": "https://www.foodstandards.gov.au/business/labelling/alcohol-labelling",
        "title": "FSANZ Alcohol Labelling Requirements"
    },
    {
        "url": "https://www.foodstandards.gov.au/business/food-safety",
        "title": "FSANZ Food Safety Requirements"
    },
    {
        "url": "https://www.foodstandards.gov.au/consumer/food-additives",
        "title": "FSANZ Food Additives Consumer Information"
    }
]


def scrape_page(url: str, title: str) -> str:
    """Scrape text content from a FSANZ webpage"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; FSANZ-Research-Bot/1.0)"}
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code != 200:
            print(f"  Failed to fetch {url} — status {response.status_code}")
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove navigation, headers, footers, scripts
        for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
            tag.decompose()

        # Get main content
        main = soup.find("main") or soup.find("article") or soup.find("div", class_="content") or soup.body
        text = main.get_text(separator="\n", strip=True) if main else ""

        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return ""


def run_scraper():
    print("=" * 60)
    print("FSANZ WEBSITE SCRAPER")
    print("=" * 60)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", ". "]
    )

    # Try to load existing chunks from S3
    try:
        existing_chunks = download_json_from_s3("processed/chunks.json")
        print(f"Loaded {len(existing_chunks)} existing chunks from S3")
    except:
        existing_chunks = []
        print("No existing chunks found — starting fresh")

    new_chunks = []

    for item in FSANZ_URLS:
        url   = item["url"]
        title = item["title"]

        print(f"\nScraping: {title}")
        print(f"  URL: {url}")

        text = scrape_page(url, title)

        if not text or len(text) < 100:
            print(f"  No content found — skipping")
            continue

        chunks = splitter.split_text(text)
        print(f"  Created {len(chunks)} chunks")

        for chunk in chunks:
            new_chunks.append({
                "text":   chunk,
                "page":   0,
                "source": title,
                "url":    url
            })

        time.sleep(2)  # Be polite — wait between requests

    if not new_chunks:
        print("\nNo new content scraped. Check your internet connection.")
        return

    # Combine with existing chunks
    all_chunks = existing_chunks + new_chunks
    print(f"\nTotal chunks: {len(existing_chunks)} existing + {len(new_chunks)} new = {len(all_chunks)}")

    # Upload combined chunks to S3
    upload_json_to_s3(data=all_chunks, s3_key="processed/chunks.json")
    print("Uploaded combined chunks to S3")

    # Save locally as backup
    with open("../data/processed/chunks_with_web.json", "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
    print("Saved local backup to data/processed/chunks_with_web.json")

    print("\nDone! Now run embed_and_index.py to add new chunks to Pinecone.")
    print("=" * 60)


if __name__ == "__main__":
    run_scraper()
