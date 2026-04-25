import os
import json
import math
import statistics
from typing import List, Dict, Any

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from bert_score import score as bertscore_score

load_dotenv(dotenv_path="../.env")


# =========================================================
# CONFIG
# =========================================================
PINECONE_INDEX_NAME = "fsanz-index"
TOP_K = 5


# =========================================================
# QUERY SETS
# =========================================================
QA_TEST_QUERIES = [
    {
        "id": "Q1",
        "question": "Is potassium sorbate allowed in fruit juice?",
        "keywords": ["potassium sorbate", "sorbate", "preservative"]
    },
    {
        "id": "Q2",
        "question": "What allergens must be declared on labels?",
        "keywords": ["allergen", "allergens", "declare", "label"]
    },
    {
        "id": "Q3",
        "question": "What are the nutrition information panel requirements for beverages?",
        "keywords": ["nutrition information panel", "nutrition", "beverages"]
    },
    {
        "id": "Q4",
        "question": "What is the maximum sulfur dioxide level in wine?",
        "keywords": ["sulfur dioxide", "wine", "maximum"]
    },
    {
        "id": "Q5",
        "question": "What warning statements are required for high caffeine drinks?",
        "keywords": ["warning", "caffeine", "statement"]
    },
    {
        "id": "Q6",
        "question": "Are preservatives permitted in beverages?",
        "keywords": ["preservative", "beverage", "permitted"]
    },
    {
        "id": "Q7",
        "question": "What labelling is required for packaged food?",
        "keywords": ["labelling", "label", "packaged food"]
    },
    {
        "id": "Q8",
        "question": "Are ingredient percentages required on labels?",
        "keywords": ["percentage", "ingredient", "label"]
    },
    {
        "id": "Q9",
        "question": "What information must appear on food packaging?",
        "keywords": ["food packaging", "label", "information"]
    },
    {
        "id": "Q10",
        "question": "What are the labelling rules for beverages?",
        "keywords": ["labelling", "beverage", "label"]
    }
]

COMPLIANCE_RETRIEVAL_QUERIES = [
    {
        "id": "CQ1",
        "question": "Is potassium sorbate at 200 mg/kg permitted in beverages under FSANZ?",
        "keywords": ["potassium sorbate", "permitted", "beverages", "mg/kg"]
    },
    {
        "id": "CQ2",
        "question": "Is sulphur dioxide at 500 mg/kg allowed in wine under FSANZ standards?",
        "keywords": ["sulphur dioxide", "wine", "maximum", "mg/kg"]
    },
    {
        "id": "CQ3",
        "question": "What are the permitted levels of sodium benzoate in beverages?",
        "keywords": ["sodium benzoate", "permitted", "level", "beverage"]
    },
    {
        "id": "CQ4",
        "question": "Are preservatives like potassium sorbate allowed without specified amounts?",
        "keywords": ["preservative", "potassium sorbate", "amount", "permitted"]
    },
    {
        "id": "CQ5",
        "question": "Is caffeine at 320 mg/L compliant for formulated beverages under FSANZ?",
        "keywords": ["caffeine", "formulated", "beverages", "mg/l"]
    },
    {
        "id": "CQ6",
        "question": "What is the maximum permitted level of caffeine in beverages under FSANZ?",
        "keywords": ["caffeine", "maximum", "level", "beverages"]
    },
    {
        "id": "CQ7",
        "question": "Are food additives like citric acid permitted in beverages?",
        "keywords": ["citric acid", "additive", "permitted", "beverages"]
    },
    {
        "id": "CQ8",
        "question": "What conditions apply to the use of preservatives in fruit juice products?",
        "keywords": ["preservatives", "fruit juice", "conditions", "use"]
    },
    {
        "id": "CQ9",
        "question": "Are there limits on sulphites in food and beverages under FSANZ?",
        "keywords": ["sulphites", "limits", "food", "beverages"]
    },
    {
        "id": "CQ10",
        "question": "What FSANZ standards regulate the use of additives in beverages?",
        "keywords": ["FSANZ", "additives", "beverages", "standards"]
    }
]

ALL_KEYWORD_QUERIES = QA_TEST_QUERIES + COMPLIANCE_RETRIEVAL_QUERIES


# =========================================================
# GROUND-TRUTH SUBSET
# =========================================================
GROUND_TRUTH_QUERIES = [
    {
        "id": "GT1",
        "question": "What allergens must be declared on labels?",
        "expected_pages": [72, 73, 74, 75],
        "expected_phrases": [
            "mandatory declarations",
            "mandatory declarations of certain foods",
            "allergen",
            "contains"
        ],
        "reference_text": (
            "Certain foods and substances must be declared on labels as mandatory "
            "declarations, including allergens and related substances."
        )
    },
    {
        "id": "GT2",
        "question": "What are the nutrition information panel requirements for beverages?",
        "expected_pages": [103, 105, 106],
        "expected_phrases": [
            "nutrition information panel",
            "nutrition information requirements",
            "serving",
            "average energy content",
            "sodium"
        ],
        "reference_text": (
            "Food for sale must provide a nutrition information panel that includes "
            "prescribed nutrition information such as energy and nutrient values per "
            "serving or per quantity."
        )
    },
    {
        "id": "GT3",
        "question": "What is the maximum sulfur dioxide level in wine?",
        "expected_pages": [586, 587],
        "expected_phrases": [
            "wine, sparkling wine and fortified wine",
            "sulphur dioxide",
            "sulphites",
            "400",
            "250"
        ],
        "reference_text": (
            "For wine, sparkling wine and fortified wine, sulphur dioxide and sulphites "
            "are permitted up to specified maximum levels depending on residual sugar content."
        )
    },
    {
        "id": "GT4",
        "question": "What warning statements are required for high caffeine drinks?",
        "expected_pages": [215, 216, 822],
        "expected_phrases": [
            "formulated caffeinated beverages",
            "required advisory statements",
            "contains caffeine",
            "not recommended for children",
            "pregnant or lactating women",
            "individuals sensitive to caffeine"
        ],
        "reference_text": (
            "Formulated caffeinated beverages must include required advisory statements, "
            "including that the product contains caffeine and is not recommended for "
            "children, pregnant or lactating women, or individuals sensitive to caffeine."
        )
    },
    {
        "id": "GT5",
        "question": "Are ingredient percentages required on labels?",
        "expected_pages": [114, 115, 116],
        "expected_phrases": [
            "characterising ingredients",
            "declaration of characterising ingredients and components",
            "percentage",
            "statement of ingredients",
            "must immediately follow"
        ],
        "reference_text": (
            "Characterising ingredients or components may need to be declared as percentages "
            "in the statement of ingredients when required by the Code."
        )
    }
]


# =========================================================
# METRICS
# =========================================================
def dcg(relevance_scores: List[int]) -> float:
    score = 0.0
    for i, rel in enumerate(relevance_scores):
        score += rel / math.log2(i + 2)
    return score


def ndcg_at_k(relevance_scores: List[int], k: int) -> float:
    actual = relevance_scores[:k]
    ideal = sorted(actual, reverse=True)

    actual_dcg = dcg(actual)
    ideal_dcg = dcg(ideal)

    if ideal_dcg == 0:
        return 0.0
    return actual_dcg / ideal_dcg


def precision_at_k(relevance_scores: List[int], k: int) -> float:
    actual = relevance_scores[:k]
    return sum(actual) / k if k > 0 else 0.0


def recall_at_k(relevance_scores: List[int], k: int) -> float:
    actual = relevance_scores[:k]
    return 1.0 if any(actual) else 0.0


def hit_at_k(relevance_scores: List[int], k: int) -> float:
    actual = relevance_scores[:k]
    return 1.0 if any(actual) else 0.0


def compute_bertscore(candidate_text: str, reference_text: str) -> Dict[str, float]:
    try:
        P, R, F1 = bertscore_score(
            [candidate_text],
            [reference_text],
            lang="en",
            verbose=False
        )
        return {
            "bertscore_precision": round(float(P[0]), 4),
            "bertscore_recall": round(float(R[0]), 4),
            "bertscore_f1": round(float(F1[0]), 4)
        }
    except Exception as e:
        return {
            "bertscore_precision": None,
            "bertscore_recall": None,
            "bertscore_f1": None,
            "bertscore_error": str(e)
        }


# =========================================================
# HELPERS
# =========================================================
_model = None
_index = None


def get_model():
    global _model
    if _model is None:
        print("Loading embedding model...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def get_index():
    global _index
    if _index is None:
        print("Connecting to Pinecone index...")
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        _index = pc.Index(PINECONE_INDEX_NAME)
    return _index


def query_index(question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    model = get_model()
    index = get_index()

    question_vector = model.encode(question).tolist()

    results = index.query(
        vector=question_vector,
        top_k=top_k,
        include_metadata=True
    )

    return results["matches"]


# =========================================================
# KEYWORD-BASED EVALUATION
# =========================================================
def evaluate_keyword_retrieval(test_queries: List[Dict[str, Any]], top_k: int = 5, group_name: str = "all") -> Dict[str, Any]:
    per_query_results = []
    precision_scores = []
    recall_scores = []
    ndcg_scores = []

    for item in test_queries:
        question = item["question"]
        keywords = [kw.lower() for kw in item["keywords"]]

        matches = query_index(question, top_k=top_k)

        relevance_scores = []
        retrieved_pages = []
        top_results = []

        for rank, match in enumerate(matches, start=1):
            text = match["metadata"].get("text", "")
            text_lower = text.lower()
            page = match["metadata"].get("page", "")
            score = match.get("score", None)

            matched_keywords = [kw for kw in keywords if kw in text_lower]
            relevance = 1 if matched_keywords else 0

            relevance_scores.append(relevance)
            retrieved_pages.append(page)

            top_results.append({
                "rank": rank,
                "page": page,
                "score": score,
                "matched_keywords": matched_keywords,
                "preview": text_lower[:300]
            })

        p_at_5 = precision_at_k(relevance_scores, top_k)
        r_at_5 = recall_at_k(relevance_scores, top_k)
        n_at_5 = ndcg_at_k(relevance_scores, top_k)

        precision_scores.append(p_at_5)
        recall_scores.append(r_at_5)
        ndcg_scores.append(n_at_5)

        per_query_results.append({
            "id": item["id"],
            "question": question,
            "keywords": keywords,
            "retrieved_pages": retrieved_pages,
            "relevance_scores": relevance_scores,
            "precision_at_5": round(p_at_5, 4),
            "recall_at_5": round(r_at_5, 4),
            "ndcg_at_5": round(n_at_5, 4),
            "top_results": top_results
        })

    return {
        "method": "keyword_based",
        "group_name": group_name,
        "num_queries": len(test_queries),
        "top_k": top_k,
        "avg_precision_at_5": round(statistics.mean(precision_scores), 4) if precision_scores else 0.0,
        "avg_recall_at_5": round(statistics.mean(recall_scores), 4) if recall_scores else 0.0,
        "avg_ndcg_at_5": round(statistics.mean(ndcg_scores), 4) if ndcg_scores else 0.0,
        "per_query_results": per_query_results
    }


# =========================================================
# GROUND-TRUTH EVALUATION
# =========================================================
def evaluate_ground_truth_subset(gt_queries: List[Dict[str, Any]], top_k: int = 5) -> Dict[str, Any]:
    per_query_results = []
    hit_scores = []
    mrr_scores = []
    ndcg_scores = []
    bert_f1_scores = []

    for item in gt_queries:
        question = item["question"]
        expected_pages = item["expected_pages"]
        expected_phrases = [p.lower() for p in item.get("expected_phrases", [])]
        reference_text = item.get("reference_text", "").strip()

        matches = query_index(question, top_k=top_k)

        relevance_scores = []
        reciprocal_rank = 0.0
        top_results = []

        best_candidate_text = ""
        best_rank = None

        for rank, match in enumerate(matches, start=1):
            text = match["metadata"].get("text", "")
            text_lower = text.lower()
            page = match["metadata"].get("page", "")
            score = match.get("score", None)

            page_match = page in expected_pages
            phrase_match = any(phrase in text_lower for phrase in expected_phrases)

            relevant = 1 if (page_match or phrase_match) else 0
            relevance_scores.append(relevant)

            if relevant == 1 and reciprocal_rank == 0.0:
                reciprocal_rank = 1.0 / rank
                best_candidate_text = text
                best_rank = rank

            top_results.append({
                "rank": rank,
                "page": page,
                "score": score,
                "page_match": page_match,
                "phrase_match": phrase_match,
                "preview": text_lower[:300]
            })

        if not best_candidate_text and matches:
            best_candidate_text = matches[0]["metadata"].get("text", "")
            best_rank = 1

        hit = hit_at_k(relevance_scores, top_k)
        ndcg_score = ndcg_at_k(relevance_scores, top_k)

        hit_scores.append(hit)
        mrr_scores.append(reciprocal_rank)
        ndcg_scores.append(ndcg_score)

        bertscore_results = {}
        if reference_text and best_candidate_text:
            bertscore_results = compute_bertscore(best_candidate_text, reference_text)
            if bertscore_results.get("bertscore_f1") is not None:
                bert_f1_scores.append(bertscore_results["bertscore_f1"])
        else:
            bertscore_results = {
                "bertscore_precision": None,
                "bertscore_recall": None,
                "bertscore_f1": None
            }

        per_query_results.append({
            "id": item["id"],
            "question": question,
            "expected_pages": expected_pages,
            "expected_phrases": expected_phrases,
            "reference_text": reference_text,
            "best_candidate_rank": best_rank,
            "relevance_scores": relevance_scores,
            "hit_at_5": round(hit, 4),
            "mrr": round(reciprocal_rank, 4),
            "ndcg_at_5": round(ndcg_score, 4),
            **bertscore_results,
            "top_results": top_results
        })

    return {
        "method": "ground_truth_subset",
        "num_queries": len(gt_queries),
        "top_k": top_k,
        "avg_hit_at_5": round(statistics.mean(hit_scores), 4) if hit_scores else 0.0,
        "avg_mrr": round(statistics.mean(mrr_scores), 4) if mrr_scores else 0.0,
        "avg_ndcg_at_5": round(statistics.mean(ndcg_scores), 4) if ndcg_scores else 0.0,
        "avg_bertscore_f1": round(statistics.mean(bert_f1_scores), 4) if bert_f1_scores else None,
        "per_query_results": per_query_results
    }


# =========================================================
# SAVE + PRINT
# =========================================================
def save_results(output_path: str, results: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def print_keyword_summary(results: Dict[str, Any]) -> None:
    print(f"\n=== Keyword-Based Retrieval Evaluation: {results['group_name']} ===")
    print(f"Number of queries   : {results['num_queries']}")
    print(f"Top-k               : {results['top_k']}")
    print(f"Average Precision@5 : {results['avg_precision_at_5']}")
    print(f"Average Recall@5    : {results['avg_recall_at_5']}")
    print(f"Average NDCG@5      : {results['avg_ndcg_at_5']}")


def print_ground_truth_summary(results: Dict[str, Any]) -> None:
    print("\n=== Ground-Truth Subset Evaluation ===")
    print(f"Number of queries      : {results['num_queries']}")
    print(f"Top-k                  : {results['top_k']}")
    print(f"Average Hit@5          : {results['avg_hit_at_5']}")
    print(f"Average MRR            : {results['avg_mrr']}")
    print(f"Average NDCG@5         : {results['avg_ndcg_at_5']}")
    print(f"Average BERTScore F1   : {results['avg_bertscore_f1']}")


# =========================================================
# MAIN
# =========================================================
def main():
    output_path = os.path.join("evaluation_outputs", "retrieval_evaluation_results.json")

    print("=== Retrieval Evaluation Started ===")
    print(f"Using Pinecone index: {PINECONE_INDEX_NAME}")

    qa_keyword_results = evaluate_keyword_retrieval(
        QA_TEST_QUERIES,
        top_k=TOP_K,
        group_name="regulatory_qa_queries"
    )

    compliance_keyword_results = evaluate_keyword_retrieval(
        COMPLIANCE_RETRIEVAL_QUERIES,
        top_k=TOP_K,
        group_name="compliance_oriented_queries"
    )

    combined_keyword_results = evaluate_keyword_retrieval(
        ALL_KEYWORD_QUERIES,
        top_k=TOP_K,
        group_name="all_queries_combined"
    )

    ground_truth_results = evaluate_ground_truth_subset(
        GROUND_TRUTH_QUERIES,
        top_k=TOP_K
    )

    final_results = {
        "index_name": PINECONE_INDEX_NAME,
        "keyword_evaluation": {
            "qa_queries": qa_keyword_results,
            "compliance_queries": compliance_keyword_results,
            "combined_queries": combined_keyword_results
        },
        "ground_truth_evaluation": ground_truth_results
    }

    save_results(output_path, final_results)

    print("\n=== Retrieval Evaluation Completed ===")
    print_keyword_summary(qa_keyword_results)
    print_keyword_summary(compliance_keyword_results)
    print_keyword_summary(combined_keyword_results)
    print_ground_truth_summary(ground_truth_results)
    print(f"\nDetailed results saved to: {output_path}")


if __name__ == "__main__":
    main()