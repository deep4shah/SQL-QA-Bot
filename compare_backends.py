"""
compare_backends.py
Runs the same set of test questions through both the Ollama (local) and
Gemini (hosted) backends, and prints a side-by-side comparison of:
- whether each succeeded
- how many attempts it took
- how long it took
- the SQL generated

Run with: python compare_backends.py
"""

from text_to_sql import ask

TEST_QUESTIONS = [
    "What is the average payment value by state?",
    "What are the top 5 product categories by total sales revenue?",
    "What is the average delivery delay in days, comparing estimated delivery date to actual delivery date?",
]

BACKENDS = ["ollama", "gemini"]


def run_comparison():
    results = []

    for question in TEST_QUESTIONS:
        print(f"\n{'=' * 70}")
        print(f"Question: {question}")
        print(f"{'=' * 70}")

        for backend in BACKENDS:
            print(f"\n--- {backend.upper()} ---")
            try:
                result = ask(question, backend=backend)
                results.append({"question": question, **result})

                status = "FAILED" if result["error"] else "SUCCESS"
                print(f"Status: {status}")
                print(f"Time: {result['time_seconds']}s | Attempts: {result['attempts']}")
                print(f"SQL: {result['sql']}")
                if result["error"]:
                    print(f"Error: {result['error']}")
                else:
                    print(f"Answer: {result['answer'][:200]}")

            except Exception as e:
                print(f"Status: CRASHED - {e}")
                results.append({
                    "question": question,
                    "backend": backend,
                    "error": str(e),
                    "time_seconds": None,
                    "attempts": None,
                    "sql": None,
                })

    # Summary table
    print(f"\n\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"{'Backend':<10} {'Success Rate':<15} {'Avg Time (s)':<15} {'Avg Attempts':<15}")

    for backend in BACKENDS:
        backend_results = [r for r in results if r["backend"] == backend]
        successes = [r for r in backend_results if not r.get("error")]
        success_rate = f"{len(successes)}/{len(backend_results)}"

        times = [r["time_seconds"] for r in backend_results if r["time_seconds"] is not None]
        avg_time = f"{sum(times) / len(times):.2f}" if times else "N/A"

        attempts = [r["attempts"] for r in backend_results if r["attempts"] is not None]
        avg_attempts = f"{sum(attempts) / len(attempts):.2f}" if attempts else "N/A"

        print(f"{backend:<10} {success_rate:<15} {avg_time:<15} {avg_attempts:<15}")

    return results


if __name__ == "__main__":
    run_comparison()
