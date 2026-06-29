"""
text_to_sql.py
Core engine: question -> SQL -> validated -> executed -> natural language answer.

Design:
- Schema is extracted live from SQLite so the prompt always matches reality.
- LLM backend is abstracted behind generate() so we can swap Ollama <-> Claude later.
- SQL is validated to be read-only before execution (safety).
- If SQL fails (bad syntax / wrong column), we feed the error back to the LLM
  and let it retry, up to MAX_RETRIES times.
"""

import sqlite3
import re
import os
import time
import ollama
from google import genai

DB_PATH = r"E:\Temp\PER\Query_rag\olist.db"
OLLAMA_MODEL_NAME = "qwen2.5-coder:7b"
GEMINI_MODEL_NAME = "gemini-2.5-flash"
MAX_RETRIES = 3

# Gemini client is created lazily (only when the gemini backend is actually
# used), so Ollama-only usage works fine even without a Gemini key set.
_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable not set. "
                "Run: setx GEMINI_API_KEY \"your-key-here\" and restart your terminal."
            )
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client

# Keywords that indicate a non-read-only / unsafe query
FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
    "CREATE", "REPLACE", "TRUNCATE", "ATTACH", "PRAGMA",
]


# ---------------------------------------------------------------------------
# LLM calls - one function per backend, plus a dispatcher. Keeping each
# backend isolated like this means the rest of the pipeline (prompt
# building, validation, retry loop) never needs to know which backend
# is in use.
# ---------------------------------------------------------------------------
def _generate_ollama(prompt: str) -> str:
    response = ollama.generate(model=OLLAMA_MODEL_NAME, prompt=prompt)
    return response["response"]


def _generate_gemini(prompt: str) -> str:
    client = _get_gemini_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=prompt,
    )
    return response.text


def generate(prompt: str, backend: str = "ollama") -> str:
    if backend == "ollama":
        return _generate_ollama(prompt)
    elif backend == "gemini":
        return _generate_gemini(prompt)
    else:
        raise ValueError(f"Unknown backend: {backend}. Use 'ollama' or 'gemini'.")


# ---------------------------------------------------------------------------
# Schema extraction
# ---------------------------------------------------------------------------
def get_schema(conn: sqlite3.Connection) -> str:
    """Builds a text description of every table and its columns/types."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]

    schema_lines = []
    for table in tables:
        cur.execute(f"PRAGMA table_info('{table}')")
        columns = cur.fetchall()  # (cid, name, type, notnull, dflt_value, pk)
        col_desc = ", ".join(f"{col[1]} ({col[2]})" for col in columns)
        schema_lines.append(f"Table: {table}\n  Columns: {col_desc}")

    # Explicit relationship hints. Column-name matching alone is not a
    # reliable enough signal for smaller local models to infer join paths,
    # especially multi-hop joins (e.g. customers -> orders -> order_payments).
    relationships = """
Relationships (foreign keys):
- orders.customer_id -> customers.customer_id
- order_items.order_id -> orders.order_id
- order_items.product_id -> products.product_id
- order_items.seller_id -> sellers.seller_id
- order_payments.order_id -> orders.order_id
- order_reviews.order_id -> orders.order_id

Important: customers and order_payments are NOT directly related.
To connect customer info (e.g. customer_state) with payments, you MUST
join through orders: customers -> orders -> order_payments.
Similarly, to connect products or sellers to orders/payments/reviews,
you MUST join through order_items.
"""

    return "\n\n".join(schema_lines) + "\n" + relationships


# ---------------------------------------------------------------------------
# SQL generation
# ---------------------------------------------------------------------------
def build_sql_prompt(schema: str, question: str, error_feedback: str = "") -> str:
    error_block = ""
    if error_feedback:
        error_block = f"""
The previous SQL query you generated failed with this error:
{error_feedback}

Please fix the query and try again.
"""

    return f"""You are a SQLite expert. Given the database schema below, write a single
SQL query that answers the user's question.

Schema:
{schema}

Rules:
- Only generate SELECT statements. Never modify data.
- Use proper JOINs based on the schema (foreign key relationships are implied by matching column names like order_id, customer_id, product_id, seller_id).
- Return ONLY the SQL query, no explanation, no markdown formatting, no backticks.
- Be careful with calculations: only combine columns when the combination is
  semantically meaningful. For example, "total sales revenue" means
  SUM(price), NOT price multiplied by freight_value or any other unrelated
  column. freight_value is a shipping cost, separate from the sale price.
  Do not multiply or combine columns together unless the question explicitly
  asks for a derived value (e.g. "price including shipping" would be
  price + freight_value, not price * freight_value).
{error_block}
Question: {question}

SQL query:"""


def extract_sql(raw_response: str) -> str:
    """Strips markdown code fences if the model added them anyway."""
    cleaned = raw_response.strip()
    cleaned = re.sub(r"^```sql\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned)
    return cleaned.strip()


def is_safe_sql(sql: str) -> bool:
    upper_sql = sql.upper()
    if not upper_sql.strip().startswith("SELECT"):
        return False
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper_sql):
            return False
    return True


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
def run_sql(conn: sqlite3.Connection, sql: str):
    """Returns (columns, rows) on success. Raises sqlite3.Error on failure."""
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description] if cur.description else []
    return columns, rows


# ---------------------------------------------------------------------------
# Natural language answer generation
# ---------------------------------------------------------------------------
def build_answer_prompt(question: str, columns: list, rows: list) -> str:
    if not rows:
        return f"""The user asked: "{question}"

The query returned no rows. Tell the user no matching data was found.
Do not invent any data."""

    # Limit how many rows we show the LLM to keep prompts small
    preview_rows = rows[:20]
    table_str = " | ".join(columns) + "\n"
    table_str += "\n".join(" | ".join(str(v) for v in row) for row in preview_rows)

    note = ""
    if len(rows) > 20:
        note = f"\n(Note: showing first 20 of {len(rows)} total rows)"

    return f"""The user asked: "{question}"

Here is the ACTUAL data returned by the database query. These are real
numbers, not an example:

{table_str}
{note}

Using ONLY the exact numbers shown above, write a clear, concise answer
to the user's question. You must reference the specific values from the
table above. Do NOT invent placeholder examples like "State A" or made-up
numbers. Do not mention SQL or databases in your answer."""


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def ask(question: str, backend: str = "ollama") -> dict:
    """
    Runs the full pipeline using the specified backend ("ollama" or "gemini").
    Returns a dict with:
    - sql: the final SQL query used
    - columns, rows: raw query result
    - answer: natural language answer
    - error: set if all retries failed
    - backend: which backend was used
    - time_seconds: total time taken
    """
    start_time = time.time()
    conn = sqlite3.connect(DB_PATH)
    schema = get_schema(conn)

    error_feedback = ""
    sql = ""

    for attempt in range(1, MAX_RETRIES + 1):
        prompt = build_sql_prompt(schema, question, error_feedback)
        raw_response = generate(prompt, backend=backend)
        sql = extract_sql(raw_response)

        if not is_safe_sql(sql):
            error_feedback = "Generated query was not a safe SELECT statement."
            continue

        try:
            columns, rows = run_sql(conn, sql)
            answer_prompt = build_answer_prompt(question, columns, rows)
            answer = generate(answer_prompt, backend=backend)

            conn.close()
            return {
                "sql": sql,
                "columns": columns,
                "rows": rows,
                "answer": answer.strip(),
                "error": None,
                "attempts": attempt,
                "backend": backend,
                "time_seconds": round(time.time() - start_time, 2),
            }
        except sqlite3.Error as e:
            error_feedback = str(e)
            continue

    conn.close()
    return {
        "sql": sql,
        "columns": [],
        "rows": [],
        "answer": None,
        "error": f"Failed after {MAX_RETRIES} attempts. Last error: {error_feedback}",
        "attempts": MAX_RETRIES,
        "backend": backend,
        "time_seconds": round(time.time() - start_time, 2),
    }


if __name__ == "__main__":
    # Quick manual test from the command line
    test_question = "What is the average delivery delay in days, comparing estimated delivery date to actual delivery date?"
    result = ask(test_question, backend="gemini")

    print(f"\nQuestion: {test_question}")
    print(f"Backend: {result['backend']}")
    print(f"SQL used:\n{result['sql']}\n")
    if result["error"]:
        print(f"Error: {result['error']}")
    else:
        print(f"Answer:\n{result['answer']}")
        print(f"\n(Attempts taken: {result['attempts']}, Time: {result['time_seconds']}s)")
