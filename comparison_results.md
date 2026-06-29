# Local vs Hosted LLM: Text-to-SQL Backend Comparison

Comparison of **Ollama (qwen2.5-coder:7b, local)** vs **Gemini 2.5 Flash (hosted)**
as the SQL-generation backend for the Olist multi-table Q&A chatbot.

## Summary

| Metric            | Ollama (local) | Gemini (hosted)        |
|--------------------|---------------|-------------------------|
| Success rate       | 3/3           | 3/3                     |
| Avg response time  | 108.32s       | 7.05s (**~15x faster**) |
| Avg attempts needed | 1.33          | 1.00                    |
| Silent correctness issues | 1 found | 0 found |

## Per-question results

### Q1: What is the average payment value by state?
| | Ollama | Gemini |
|---|---|---|
| Time | 209.74s | 8.56s |
| Attempts | 2 | 1 |
| Result | Correct | Correct |

Both backends produced matching, correct results (e.g. AC: $234.29, AL: $227.08).

### Q2: What are the top 5 product categories by total sales revenue?
| | Ollama | Gemini |
|---|---|---|
| Time | 75.19s | 4.96s |
| Attempts | 1 | 1 |
| Result | Correct | Correct |

Both correctly identified `health_beauty` as #1 (~$1.26M revenue) after an earlier prompt
fix (originally the model incorrectly multiplied `price * freight_value` instead of
summing `price` alone — see "Bugs found" below).

### Q3: What is the average delivery delay in days (estimated vs actual)?
| | Ollama | Gemini |
|---|---|---|
| Time | 40.02s | 7.64s |
| Attempts | 1 | 1 |
| Result | **Incorrect (-0.0225 days)** | Correct (-11.18 days) |

**This is the most interesting finding of the comparison.** Ollama generated SQL that
subtracted two date *strings* directly (`date_a - date_b`) instead of converting them
with `julianday()` first. SQLite doesn't error on this — it just silently computes a
meaningless number. The query "succeeded" (no exception), so the automatic retry loop
never triggered, even though the answer was wrong. Gemini correctly used `julianday()`
on both sides and got the right answer.

## Bugs found and fixed during development

1. **Wrong revenue calculation** — model initially computed `SUM(price * freight_value)`
   for "total sales revenue" instead of `SUM(price)`, treating freight cost as a
   multiplier rather than a separate cost. Fixed by adding explicit calculation-semantics
   rules to the prompt.
2. **Wrong join path** — model initially joined `customers` directly to `order_payments`
   (no such relationship exists), skipping the required `orders` bridge table. Fixed by
   adding explicit foreign-key relationship documentation to the schema prompt, since
   column-name matching alone wasn't a strong enough signal for the local model.
3. **Hallucinated answer text** — when asked to phrase a natural-language answer, the
   local model sometimes invented placeholder examples ("State A: $50") instead of using
   the real returned data. Fixed by rewriting the answer prompt to explicitly state the
   numbers shown are real, not illustrative.
4. **Silent date-arithmetic error** — see Q3 above. Fixed by adding an explicit rule
   requiring `julianday()` for any date subtraction.

## Takeaways

- Gemini (hosted) was both **faster** and **more reliable** on semantically tricky
  calculations (date arithmetic) in this comparison.
- Ollama (local) is still fully capable for most queries, but local 7B-class models
  benefit significantly from very explicit prompt engineering around calculation
  semantics — vague schema hints aren't enough.
- The retry loop only catches SQL that *errors*. It does not catch SQL that *runs
  successfully but computes the wrong thing* — a known limitation worth highlighting
  rather than hiding.
