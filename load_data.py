"""
load_data.py
Loads the Olist Brazilian E-commerce CSVs into a single SQLite database.

Design decisions:
- geolocation table is skipped for now (messy many-to-many zip mapping)
- product_category_name_translation is merged directly into products,
  replacing the Portuguese category name with the English one, so the
  LLM only ever sees one clean column name when generating SQL.
"""

import sqlite3
import pandas as pd
from pathlib import Path

# ---- CONFIG: update this path to match your machine ----
DATA_DIR = Path(r"E:\Temp\PER\Query_rag\Data")
DB_PATH = Path(r"E:\Temp\PER\Query_rag\olist.db")
# ----------------------------------------------------------

TABLES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
}

CATEGORY_TRANSLATION_FILE = "product_category_name_translation.csv"


def load_csv(filename: str) -> pd.DataFrame:
    path = DATA_DIR / filename
    df = pd.read_csv(path)
    return df


def build_products_table() -> pd.DataFrame:
    """Merge English category names into products, drop the Portuguese column."""
    products = load_csv(TABLES["products"])
    translation = load_csv(CATEGORY_TRANSLATION_FILE)

    merged = products.merge(translation, on="product_category_name", how="left")
    merged = merged.drop(columns=["product_category_name"])
    merged = merged.rename(
        columns={"product_category_name_english": "product_category_name"}
    )
    return merged


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    for table_name, filename in TABLES.items():
        if table_name == "products":
            df = build_products_table()
        else:
            df = load_csv(filename)

        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"Loaded '{table_name}': {len(df):,} rows, {len(df.columns)} columns")

    # Quick sanity check: list tables and row counts
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print("\nTables in database:", [r[0] for r in cur.fetchall()])

    conn.close()
    print(f"\nDone. Database saved to: {DB_PATH}")


if __name__ == "__main__":
    main()