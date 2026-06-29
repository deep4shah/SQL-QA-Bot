"""
app.py
Streamlit UI for the Olist text-to-SQL chatbot.

Run with: streamlit run app.py
"""

import streamlit as st
from text_to_sql import ask

st.set_page_config(page_title="Olist Data Q&A", page_icon="📊", layout="centered")

st.title("📊 Olist E-commerce Data Q&A")
st.caption(
    "Ask questions about the Olist Brazilian e-commerce dataset in plain English. "
    "Each question is answered independently (no conversation memory yet)."
)

with st.expander("ℹ️ About this dataset"):
    st.write(
        """
        This chatbot answers questions over the **Olist Brazilian E-commerce** dataset,
        covering customers, orders, order items, payments, reviews, products, and sellers.

        Example questions to try:
        - What is the average payment value by state?
        - What are the top 5 product categories by total sales revenue?
        - Which product category has the most 1-star reviews?
        - What is the average delivery delay in days?
        """
    )

question = st.text_input(
    "Ask a question about the data:",
    placeholder="e.g. What are the top 5 product categories by total sales revenue?",
)

backend = st.selectbox(
    "LLM backend:",
    options=["ollama", "gemini"],
    format_func=lambda b: "🖥️ Ollama (local, free)" if b == "ollama" else "☁️ Gemini (hosted, free tier)",
)

ask_button = st.button("Ask", type="primary")

if ask_button and question.strip():
    with st.spinner(f"Generating SQL and querying the database using {backend}..."):
        result = ask(question, backend=backend)

    if result["error"]:
        st.error(f"Couldn't answer this question.\n\n{result['error']}")
        if result["sql"]:
            st.subheader("Last SQL attempted")
            st.code(result["sql"], language="sql")
    else:
        st.subheader("Answer")
        st.write(result["answer"])

        st.subheader("Generated SQL")
        st.code(result["sql"], language="sql")

        st.caption(
            f"Backend: {result['backend']} | "
            f"Time: {result['time_seconds']}s | "
            f"Attempts: {result['attempts']}"
        )

        with st.expander("📋 Raw query result"):
            if result["rows"]:
                st.dataframe(
                    [dict(zip(result["columns"], row)) for row in result["rows"]]
                )
            else:
                st.write("No rows returned.")

elif ask_button:
    st.warning("Please enter a question first.")
