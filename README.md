# 🍽️ FSANZ Regulatory Affairs Assistant

An AI-powered chatbot that helps users navigate **Food Standards Australia New Zealand (FSANZ)** regulations using Retrieval-Augmented Generation (RAG). Built as part of a Master of Data Science group project.

---

## 📌 What It Does

- 💬 **Chat with FSANZ regulations** — Ask any question about food labelling, additives, allergens, and standards
- ✅ **AI Compliance Checker** — Paste an ingredient list and instantly check if it complies with FSANZ rules
- ☁️ **Cloud-powered** — All documents, logs, and data are stored securely in AWS S3
- 🔍 **Semantic Search** — Uses vector embeddings to find the most relevant regulatory sections
- 📋 **Detailed Reports** — Get PASS / WARNING / FAIL results per ingredient with recommendations

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **LLM** | Anthropic Claude (claude-sonnet-4-6) |
| **Vector Database** | Pinecone |
| **Embeddings** | SentenceTransformer (all-MiniLM-L6-v2) |
| **Cloud Storage** | AWS S3 |
| **Backend API** | FastAPI (Python) |
| **Frontend UI** | Streamlit |
| **PDF Parsing** | PyMuPDF (fitz) |
| **Text Chunking** | LangChain RecursiveCharacterTextSplitter |

---

## 📁 Project Structure

```
FSANZ-Assistant/
│
├── backend/
│   ├── aws_helper.py          # AWS S3 upload/download utilities
│   ├── parse_pdf.py           # PDF text extraction and chunking
│   ├── embed_and_index.py     # Vector embeddings and Pinecone indexing
│   ├── rag_pipeline.py        # RAG pipeline — search + generate answers
│   ├── compliance_checker.py  # AI Compliance Checker module
│   └── main.py                # FastAPI backend server
│
├── frontend/
│   └── ui.py                  # Streamlit chat UI with compliance tab
│
├── data/
│   └── raw/                   # Local storage for PDFs and chunks
│
├── .env                       # API keys (NOT pushed to GitHub)
├── requirements.txt           # Python dependencies
└── README.md
```

---

## ⚙️ Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/FSANZ-Regulatory-Assistant.git
cd FSANZ-Regulatory-Assistant
```

### 2. Create and Activate Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Create Your `.env` File

Create a file called `.env` in the root folder with the following:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
PINECONE_API_KEY=your_pinecone_api_key_here
AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_key_here
AWS_REGION=ap-southeast-2
S3_BUCKET=your_s3_bucket_name_here
```

> ⚠️ **Never share or commit your `.env` file. It contains sensitive API keys.**

### 5. Set Up AWS S3

- Create an S3 bucket (e.g., `fsanz-assistant-project`)
- Upload the FSANZ Food Standards PDF to the bucket under `raw/`

### 6. Set Up Pinecone

- Create a free account at [pinecone.io](https://www.pinecone.io)
- Create an index with:
  - **Dimensions:** 384
  - **Metric:** cosine
  - **Index name:** `fsanz-index`

---

## 🚀 Running the Project

### Step 1 — Parse and Chunk the PDF

```bash
python backend/parse_pdf.py
```

### Step 2 — Embed and Index to Pinecone

```bash
python backend/embed_and_index.py
```

### Step 3 — Start the Backend API

Open a terminal and run:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### Step 4 — Start the Frontend UI

Open a **second terminal** and run:

```bash
streamlit run frontend/ui.py
```

Then open your browser and go to: **http://localhost:8501**

---

## 💡 Features

### 🗨️ Chat Assistant Tab
- Ask natural language questions about FSANZ food standards
- Get AI-generated answers backed by the actual regulatory document
- Example questions are provided in the sidebar

### ✅ Compliance Checker Tab
- Paste any ingredient list (e.g., from a food label)
- The AI extracts each ingredient and checks it against FSANZ regulations
- Results show:
  - ✅ **PASS** — Compliant with standards
  - ⚠️ **WARNING** — Potential issue, review recommended
  - ❌ **FAIL** — Non-compliant, action required
- Full compliance report is saved to AWS S3

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Check if backend is running |
| POST | `/ask` | Ask a regulatory question |
| POST | `/check-compliance` | Run compliance check on ingredients |

---

## 📊 How It Works (RAG Pipeline)

```
User Question
     ↓
Convert to Vector Embedding (SentenceTransformer)
     ↓
Search Pinecone for Top 5 Relevant Chunks
     ↓
Send Context + Question to Claude LLM
     ↓
Generate Answer
     ↓
Log Q&A to AWS S3
     ↓
Display to User
```

---

## 🔐 Security Notes

- `.env` file is listed in `.gitignore` and will **not** be pushed to GitHub
- Never hardcode API keys in any Python file
- Rotate your API keys if they are ever accidentally exposed

---

## 👥 Team

Built by a group of 5 Master of Data Science students as part of a 12-week group project.

---

## 📄 Dataset

- **FSANZ Food Standards Code — Compilation (March 2025)**
- Source: [foodstandards.gov.au](https://www.foodstandards.gov.au)

---

## 📝 License

This project is for academic purposes only. FSANZ regulatory content belongs to Food Standards Australia New Zealand.
