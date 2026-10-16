# Day 5 — Retrieval Evaluation Dataset

> [!NOTE]
> **Baseline metrics in this document are placeholders.** All `TBD` values in the [Baseline Results](#baseline-results) table must be filled in after running the evaluation pipeline against a real processed document. See [How to Run](#how-to-run) for instructions.

---

## Introduction

This document defines the **retrieval evaluation dataset** for the Document Q&A system. It is used to measure and compare the quality of three retrieval strategies:

| Strategy | Description |
|---|---|
| **BM25** | Sparse keyword-based retrieval using term frequency–inverse document frequency scoring |
| **Semantic Search** | Dense vector retrieval using embedding similarity (cosine distance) |
| **Hybrid RRF** | Reciprocal Rank Fusion combining BM25 and semantic rankings |

### Purpose

The goal of this dataset is to answer the following questions systematically:

- Which retrieval mode surfaces the **most relevant chunks** in the top-K results?
- Where does each mode fail — on exact terms, paraphrased queries, or out-of-scope questions?
- What is the **latency vs. quality trade-off** between modes?
- Does the system correctly **abstain** when evidence is absent?

### How to Use

1. Load a real contract or legal document into the system and note its `document_id`.
2. Run each of the 15 questions below against all three retrieval modes using the search endpoint.
3. For each query, record whether the correct chunk appears in the top-5 results and at what rank.
4. Fill in the [Baseline Results](#baseline-results) table with computed metrics.
5. Record observations in the [Key Observations](#key-observations) section.

> [!IMPORTANT]
> These questions are written for a **generic contract document** (e.g., a service agreement or SaaS subscription contract). If your test document is a different type, adapt the exact-term questions (Q1–Q5) to match real clause numbers, dates, and figures present in that document.

---

## Evaluation Questions

> [!TIP]
> **Question Types at a Glance**
> - **Exact-Term** — wording likely mirrors what's in the document verbatim; tests BM25's keyword strength.
> - **Paraphrased** — semantically equivalent but differently worded; tests semantic/hybrid recall.
> - **Absent-Evidence** — answer is not in a typical contract; the system should abstain rather than hallucinate.

| # | Question | Type | Expected Behavior | Notes |
|---|---|---|---|---|
| 1 | What is the termination notice period specified in Section 12.3? | Exact-Term | Retrieve the chunk containing Section 12.3 in top-5 | Exact clause reference tests BM25 keyword recall |
| 2 | What are the payment terms defined under Clause 5? | Exact-Term | Retrieve the chunk containing Clause 5 payment terms in top-5 | Tests retrieval of a numbered clause |
| 3 | What does the contract define as "Confidential Information"? | Exact-Term | Return the definitions clause chunk with the exact phrase | Quoted defined term should be a strong BM25 signal |
| 4 | What is the total contract value stated in Schedule A? | Exact-Term | Retrieve Schedule A or pricing annex chunk in top-5 | Tests retrieval of schedule/appendix sections |
| 5 | What is the effective date of the agreement? | Exact-Term | Return the preamble or recitals chunk containing the date | Short factual exact-term lookup |
| 6 | How long does a party need to give notice before ending the contract? | Paraphrased | Retrieve the termination/notice period chunk in top-5 | Paraphrase of Q1 — tests semantic over keyword matching |
| 7 | When does the customer have to pay the vendor? | Paraphrased | Retrieve payment terms chunk in top-5 | Paraphrase of Q2 — avoids "payment terms" and "Clause 5" |
| 8 | What information is the receiving party not allowed to disclose? | Paraphrased | Return confidentiality clause chunk in top-5 | Paraphrase of Q3 — tests semantic understanding of legal concept |
| 9 | How much money is this contract worth in total? | Paraphrased | Retrieve pricing/schedule chunk in top-5 | Paraphrase of Q4 — casual language vs. formal contract text |
| 10 | When did both parties agree to start this contract? | Paraphrased | Return preamble chunk with effective date in top-5 | Paraphrase of Q5 — tests date/event semantic retrieval |
| 11 | What are the environmental sustainability commitments of the vendor? | Absent-Evidence | System should return low-confidence results or abstain | Sustainability clauses rarely appear in standard contracts |
| 12 | What is the vendor's policy on employee mental health benefits? | Absent-Evidence | System should abstain or indicate no relevant chunk found | HR/benefits policy is out of scope for a contract document |
| 13 | How does the contract handle cryptocurrency payment options? | Absent-Evidence | System should return no confident match and abstain | Crypto payment terms not present in standard agreements |
| 14 | What are the parties' obligations under GDPR Article 35 impact assessments? | Absent-Evidence | Abstain unless a DPA is embedded; typical contracts lack this | Tests over-retrieval of tangentially related privacy clauses |
| 15 | What is the vendor's stock price at the time of signing? | Absent-Evidence | System must abstain — financial market data is never in contracts | Tests hallucination resistance on factually impossible queries |

---

## Metrics Reference

| Metric | Formula / Definition | Why It Matters |
|---|---|---|
| **Recall@K** | `(# relevant chunks in top-K) / (total relevant chunks)` | Measures whether the system finds the right evidence at all |
| **MRR** (Mean Reciprocal Rank) | `mean(1 / rank_of_first_relevant_chunk)` | Rewards systems that rank the best chunk highest |
| **nDCG@K** | Normalized discounted cumulative gain at rank K | Accounts for graded relevance and rank position together |
| **Avg Latency (ms)** | Mean wall-clock time from query to ranked results | Practical performance constraint for interactive Q&A |
| **Embedding API Calls** | Count of embedding model calls per query | Tracks cost and rate-limit exposure per retrieval mode |

> [!NOTE]
> For **Absent-Evidence** questions (Q11–Q15), a correct result is defined as either:
> - **No chunk returned** above the confidence threshold, or
> - The `/answer` endpoint responding with an abstention (e.g., `"answer": null` or low-confidence flag).
>
> Do **not** penalize recall for these questions — instead, track the **false positive rate** (chunks incorrectly returned as relevant).

---

## Baseline Results

> [!WARNING]
> All values below are `TBD`. **Do not treat these as real measurements.** Fill in this table after running the evaluation pipeline against a real processed document as described in [How to Run](#how-to-run).

| Mode | Recall@5 | MRR | nDCG@5 | Avg Latency (ms) | Embedding API Calls |
|---|---|---|---|---|---|
| BM25 | TBD | TBD | TBD | TBD | TBD |
| Semantic | TBD | TBD | TBD | TBD | TBD |
| Hybrid RRF | TBD | TBD | TBD | TBD | TBD |

**Expected hypotheses to validate after filling in:**

- BM25 should outperform on **Exact-Term** questions (Q1–Q5) due to strong keyword overlap.
- Semantic search should outperform on **Paraphrased** questions (Q6–Q10).
- Hybrid RRF should achieve the **best overall Recall@5 and nDCG@5** by combining both signals.
- All modes should score near-zero recall on **Absent-Evidence** questions (Q11–Q15).

---

## How to Run

### 1. Start the Backend

From the `backend/` directory:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`. Confirm it's healthy:

```bash
curl http://localhost:8000/health
```

---

### 2. Upload and Process a Document

If not already done, upload and process a test document to obtain its `document_id`:

```bash
# Upload
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@/path/to/your/contract.pdf"

# Note the returned document_id from the response
```

---

### 3. Run a Search Query

Use `POST /api/v1/documents/{document_id}/search` with different `mode` values to compare retrieval strategies.

**BM25 search:**
```bash
curl -X POST http://localhost:8000/api/v1/documents/{document_id}/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "termination notice period Section 12.3",
    "mode": "bm25",
    "top_k": 5
  }'
```

**Semantic search:**
```bash
curl -X POST http://localhost:8000/api/v1/documents/{document_id}/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How long does a party need to give notice before ending the contract?",
    "mode": "semantic",
    "top_k": 5
  }'
```

**Hybrid RRF:**
```bash
curl -X POST http://localhost:8000/api/v1/documents/{document_id}/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How long does a party need to give notice before ending the contract?",
    "mode": "hybrid",
    "top_k": 5
  }'
```

---

### 4. Evaluate Results

For each query and mode combination:

1. Inspect the returned `chunks` array and note the **rank** of the first relevant chunk.
2. Record whether the correct chunk appears in positions 1–5 (for Recall@5).
3. Compute MRR as `1 / rank` for the first relevant result (0 if not in top-5).
4. For Absent-Evidence questions, flag any result returned with a confidence score above your threshold as a **false positive**.

**Example response structure to evaluate:**

```json
{
  "query": "termination notice period Section 12.3",
  "mode": "bm25",
  "chunks": [
    {
      "chunk_id": "abc-123",
      "text": "12.3 Either party may terminate this Agreement...",
      "score": 0.87,
      "page": 7
    }
  ]
}
```

> [!TIP]
> Automate scoring by writing a small Python script that iterates over all 15 questions × 3 modes, calls the API, checks whether the expected `chunk_id` (manually labeled) appears in `chunks[:5]`, and computes aggregate metrics.

---

## Key Observations

*This section is intentionally left blank. Fill in after running the evaluation.*

**Suggested prompts for your notes:**

- Which retrieval mode performed best overall, and why?
- Were there surprising failures in BM25 on paraphrased queries?
- Did Hybrid RRF ever perform **worse** than either individual mode? If so, why?
- How did latency differ across modes? Is the quality gain worth the overhead?
- Did the system correctly abstain on all 5 absent-evidence questions?

---

## Citation Integrity

The `/answer` endpoint performs **citation validation** after generating a response: it checks that every source chunk cited in the answer was actually returned by the retrieval step and is present in the context window.

### What to Check

When evaluating answer quality, inspect the `invalid_citations` field in the response:

```json
{
  "answer": "The termination notice period is 30 days as specified in Section 12.3.",
  "citations": ["chunk-abc-123"],
  "invalid_citations": [],
  "confidence": 0.91
}
```

| Field | Meaning |
|---|---|
| `citations` | List of `chunk_id` values the model cited in its answer |
| `invalid_citations` | Citations that could **not** be verified against retrieved chunks |
| `confidence` | Model-reported confidence in the answer |

> [!CAUTION]
> A non-empty `invalid_citations` list means the model **hallucinated a source** — it referenced a chunk that was never retrieved or does not exist. This is a critical failure mode. Any answer with invalid citations should be treated as untrustworthy and flagged for review.

### Citation Integrity Checklist

- [ ] Run all 15 evaluation questions through `/answer` and record `invalid_citations` counts.
- [ ] Verify that Absent-Evidence questions (Q11–Q15) return either an abstention or an empty `citations` list.
- [ ] Confirm that non-empty `invalid_citations` correlates with low `confidence` scores.
- [ ] If invalid citations appear frequently, check whether the retrieval top-K is large enough to include all chunks the model needs.
