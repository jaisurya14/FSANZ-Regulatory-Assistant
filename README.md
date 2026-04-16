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
├── .env                       # API keys (NOT pushed to GitHub — keep private)
├── requirements.txt           # Python dependencies
└── README.md
```

---

## 👥 Team Setup — Quick Start (Shared Cloud)

> **Recommended for group members** — Uses the same AWS S3 and Pinecone index. No re-indexing needed.

### Step 1 — Get the `.env` file from your team leader
The `.env` file contains all API keys. Your team leader will share it privately (WhatsApp / email).
**Never commit this file to GitHub.**

Place the file in the root of the project folder:
```
FSANZ-Regulatory-Assistant/
└── .env   ← put it here
```

### Step 2 — Clone the Repository

```bash
git clone https://github.com/jaisurya14/FSANZ-Regulatory-Assistant.git
cd FSANZ-Regulatory-Assistant
```

### Step 3 — Create and Activate Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### Step 4 — Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 5 — Start the Backend (Terminal 1)

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### Step 6 — Start the Frontend (Terminal 2 — new window)

```bash
cd FSANZ-Regulatory-Assistant
streamlit run frontend/ui.py
```

Open your browser and go to: **http://localhost:8501** 🎉

---

## ⚙️ Full Setup — Own Cloud Accounts (Optional)

> Use this if you want your own independent AWS S3 and Pinecone setup.

### 1️⃣ Get Anthropic API Key (for Claude LLM)
1. Go to [console.anthropic.com](https://console.anthropic.com) → Sign up
2. Navigate to **API Keys** → Create a new key
3. Add at least **$5 credits** under Billing
4. Copy the key

### 2️⃣ Get Pinecone API Key (for vector search)
1. Go to [app.pinecone.io](https://app.pinecone.io) → Sign up (free)
2. Navigate to **API Keys** → Copy your key
3. Go to **Indexes** → Create Index with:
   - **Name:** `fsanz-index`
   - **Dimensions:** `384`
   - **Metric:** `cosine`

### 3️⃣ Set Up AWS S3 (for cloud storage)
1. Go to [aws.amazon.com](https://aws.amazon.com) → Create free account
2. Open **S3** → Create a new bucket (e.g. `fsanz-assistant-yourname`)
3. Open **IAM** → Users → Create a new user → Attach policy: `AmazonS3FullAccess`
4. Under the user → **Security credentials** → Create Access Key
5. Save your `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
6. Upload the FSANZ PDF into your S3 bucket under folder `raw/`

### 4️⃣ Create Your `.env` File

Create a file named `.env` in the root project folder:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
PINECONE_API_KEY=your_pinecone_api_key_here
AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_key_here
AWS_REGION=ap-southeast-2
S3_BUCKET=your_s3_bucket_name_here
```

### 5️⃣ Index the Data (one-time setup)

```bash
python backend/parse_pdf.py        # Extract and chunk the FSANZ PDF
python backend/embed_and_index.py  # Embed chunks and push to Pinecone
```

### 6️⃣ Run the App

**Terminal 1:**
```bash
cd backend
uvicorn main:app --reload --port 8000
```

**Terminal 2:**
```bash
streamlit run frontend/ui.py
```

Open: **http://localhost:8501**

---

## 💡 Features

### 🗨️ Chat Assistant Tab
- Ask natural language questions about FSANZ food standards
- Get AI-generated answers backed by the actual regulatory document
- Example questions provided in the sidebar

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

- `.env` file is listed in `.gitignore` — it will **never** be pushed to GitHub
- Never hardcode API keys in any Python file
- Share the `.env` file only via private channels (WhatsApp, email)
- Rotate your API keys immediately if they are ever accidentally exposed

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
