# Olist Multi-Table Q&A Chatbot (Text-to-SQL)

A natural-language Q&A chatbot over a real multi-table e-commerce database. Ask
questions in plain English, get back accurate answers backed by live SQL queries —
no manual querying required.

Built on the **Olist Brazilian E-commerce** dataset (9 relational tables, ~100K orders),
with a swappable LLM backend so the same pipeline can run fully local (Ollama) or
hosted (Gemini API).

## Overview

This project explores **text-to-SQL**: translating a user's natural-language question
into a valid SQL query, executing it safely against a real relational database, and
returning a grounded, natural-language answer — including calculations like averages,
rankings, and date-based comparisons across multiple joined tables.

It's a companion piece to my [Wiki-RAG project](#) (unstructured document Q&A via
retrieval), demonstrating the other major pattern for LLM-powered data Q&A:
**structured, relational data reasoning.**

## Features

- **Multi-table reasoning** — handles questions that require joining across customers,
  orders, order items, payments, reviews, products, and sellers
- **Calculation-aware** — correctly computes averages, sums, rankings, and date
  differences, not just simple lookups
- **Safety-validated SQL** — generated queries are checked to ensure they're
  read-only (`SELECT` only) before execution; destructive statements are blocked
- **Self-correcting retry loop** — if generated SQL fails, the error is fed back to
  the LLM for up to 3 attempts before giving up
- **Swappable LLM backend** — runs on either a fully local Ollama model
  (`qwen2.5-coder:7b`) or the hosted Gemini API, with a single parameter switch
- **Transparent UI** — the Streamlit app shows the generated SQL, response time, and
  attempt count alongside every answer, not just the final answer

## Architecture

```
User question (natural language)
        |
        v
  Schema extraction (live from SQLite, incl. explicit foreign-key hints)
        |
        v
  LLM generates SQL  <-- retry loop on failure (up to 3 attempts)
        |
        v
  Safety validation (SELECT-only, no destructive keywords)
        |
        v
  Execute against SQLite
        |
        v
  LLM phrases a grounded natural-language answer from the real results
        |
        v
  Streamlit UI displays: answer, SQL, timing, attempt count
```

## Tech stack

- **Database:** SQLite (loaded from 9 Olist CSVs via pandas)
- **LLM backends:** Ollama (`qwen2.5-coder:7b`, local) and Gemini API
  (`gemini-2.5-flash`, hosted) — swappable via a single `backend` parameter
- **UI:** Streamlit
- **Language:** Python

## Dataset

[Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(Kaggle) — 9 CSVs covering customers, orders, order items, payments, reviews,
products, and sellers from a real Brazilian marketplace.

The `geolocation` table was excluded from this version due to its messy many-to-many
zip-code mapping; product category names were merged to English directly during
loading for schema clarity.

## Setup

```bash
# 1. Clone the repo and install dependencies
pip install pandas streamlit ollama google-genai

# 2. Pull the local model (or skip if only using Gemini)
ollama pull qwen2.5-coder:7b

# 3. Set your Gemini API key (or skip if only using Ollama)
# Windows PowerShell:
setx GEMINI_API_KEY "your-key-here"

# 4. Download the Olist dataset from Kaggle and update DATA_DIR in load_data.py

# 5. Build the database
python load_data.py

# 6. Run the app
streamlit run app.py
```

## Usage

Open the Streamlit app, pick a backend (Ollama or Gemini), and ask a question, e.g.:

- "What is the average payment value by state?"
- "What are the top 5 product categories by total sales revenue?"
- "Which product category has the most 1-star reviews?"
- "What is the average delivery delay in days?"

## Local vs hosted LLM comparison

See [`comparison_results.md`](./comparison_results.md) for a full write-up. Summary:

| Metric            | Ollama (local) | Gemini (hosted)        |
|--------------------|---------------|-------------------------|
| Success rate       | 3/3           | 3/3                     |
| Avg response time  | 108.32s       | 7.05s (~15x faster)     |
| Avg attempts needed | 1.33          | 1.00                    |
| Silent correctness issues | 1 found | 0 found |

The most interesting finding: Ollama generated SQL that subtracted date *strings*
directly instead of using `julianday()`, producing a silently wrong (but
non-erroring) result. Since the retry loop only triggers on SQL *errors*, this kind
of "succeeds but wrong" failure mode required separate prompt-engineering fixes.

## Challenges & lessons learned

1. **Column-name matching isn't enough for joins.** The model initially joined
   `customers` directly to `order_payments` (no such relationship exists). Fixing
   this required explicitly documenting foreign-key relationships in the prompt,
   not just listing column names and types.
2. **Plausible SQL can compute the wrong thing.** Early version computed "total
   revenue" as `SUM(price * freight_value)` instead of `SUM(price)` — syntactically
   valid, semantically wrong. Required explicit calculation-semantics rules in the
   prompt.
3. **Smaller models can hallucinate "example" answers.** When phrasing a final
   answer, the local model sometimes invented placeholder data ("State A: $50")
   instead of grounding in the real query results. Fixed with stricter, explicit
   grounding instructions.
4. **Successful SQL execution doesn't mean correct SQL.** The retry loop only
   catches queries that raise an error — it has no way to catch a query that runs
   fine but computes something semantically wrong (e.g. the date-subtraction bug
   above). This is a known limitation of the current design.

## Future improvements

- Add conversational context so follow-up questions ("what about for São Paulo?")
  work without restating the full question
- Re-include the `geolocation` table for map-based questions
- Add a lightweight semantic validation step (not just syntactic) to catch
  "succeeds but wrong" SQL before it reaches the user
- Expand the backend comparison with more questions and additional providers

## License

MIT
