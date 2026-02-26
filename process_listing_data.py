import pandas as pd
import json
import sys


def safe_parse_json(raw):
    """Safely parse a JSON string, returning None on failure."""
    if pd.isna(raw):
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def extract_page_content_fields(raw):
    """Extract only title, category, vertical, subCategory, superCategory from page_content JSON."""
    parsed = safe_parse_json(raw)
    if parsed is None or not isinstance(parsed, dict):
        return {
            "title": None,
            "category": None,
            "vertical": None,
            "subCategory": None,
            "superCategory": None,
        }
    return {
        "title": parsed.get("title"),
        "category": parsed.get("category"),
        "vertical": parsed.get("vertical"),
        "subCategory": parsed.get("subCategory"),
        "superCategory": parsed.get("superCategory"),
    }


def flatten_revenue_history(df):
    """
    Parse monthly_revenue_history JSON arrays and flatten into rows of:
    item_id, date, revenue (renamed from avg_monthly_revenue).
    """
    records = []
    for _, row in df.iterrows():
        item_id = row["item_id"]
        parsed = safe_parse_json(row["monthly_revenue_history"])
        if parsed is None or not isinstance(parsed, list):
            continue
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            records.append({
                "item_id": item_id,
                "date": entry.get("date"),
                "revenue": entry.get("avg_monthly_revenue"),
            })
    return pd.DataFrame(records)


def flatten_promotion_history(df):
    """
    Parse promotion_history JSON arrays and flatten into rows of:
    item_id, date, price (renamed from value).
    """
    records = []
    for _, row in df.iterrows():
        item_id = row["item_id"]
        parsed = safe_parse_json(row["promotion_history"])
        if parsed is None or not isinstance(parsed, list):
            continue
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            records.append({
                "item_id": item_id,
                "date": entry.get("date"),
                "price": entry.get("value"),
            })
    return pd.DataFrame(records)


def main():
    # STEP 1: Load the CSV
    input_path = "listingdata (1).csv"
    print(f"Loading CSV: {input_path}")
    df = pd.read_csv(input_path)
    print(f"  Loaded {len(df)} rows, {len(df.columns)} columns")

    # STEP 2: Parse page_content and extract selected fields
    print("Parsing page_content JSON...")
    page_content_extracted = df["page_content"].apply(extract_page_content_fields)
    page_content_df = pd.DataFrame(page_content_extracted.tolist())
    page_content_df["item_id"] = df["item_id"].values
    page_content_df = page_content_df[["item_id", "title", "category", "vertical", "subCategory", "superCategory"]]

    metadata_cols = ["item_id", "unique_identifier", "brand_name", "rating", "rating_count", "variations_count"]
    metadata_df = df[metadata_cols].drop_duplicates(subset=["item_id"], keep="first").reset_index(drop=True)

    page_content_df = page_content_df.drop_duplicates(subset=["item_id"], keep="first").reset_index(drop=True)
    page_content_df = pd.merge(page_content_df, metadata_df, on="item_id", how="left")
    print(f"  Extracted page_content + metadata for {len(page_content_df)} unique items")

    # STEP 3: Flatten revenue_history
    print("Flattening revenue history...")
    revenue_df = flatten_revenue_history(df)
    print(f"  Revenue rows: {len(revenue_df)}")

    # STEP 4: Flatten promotion_history
    print("Flattening promotion history...")
    promotion_df = flatten_promotion_history(df)
    print(f"  Promotion rows: {len(promotion_df)}")

    # STEP 5: Convert date columns to datetime
    print("Converting date columns to datetime...")
    if not revenue_df.empty:
        revenue_df["date"] = pd.to_datetime(revenue_df["date"], errors="coerce")
    if not promotion_df.empty:
        promotion_df["date"] = pd.to_datetime(promotion_df["date"], errors="coerce")

    # STEP 6: Merge revenue and price on item_id + date (LEFT JOIN)
    print("Merging revenue and promotion data...")
    merged_df = pd.merge(revenue_df, promotion_df, on=["item_id", "date"], how="left")
    print(f"  Merged rows: {len(merged_df)}")

    # STEP 7: Forward fill price per item_id where price is null
    print("Forward filling price per item_id...")
    merged_df = merged_df.sort_values(by=["item_id", "date"]).reset_index(drop=True)
    merged_df["price"] = merged_df.groupby("item_id")["price"].ffill()

    # STEP 8: Merge with page_content fields on item_id
    print("Merging with page_content fields...")
    final_df = pd.merge(merged_df, page_content_df, on="item_id", how="left")
    print(f"  Final rows after page_content merge: {len(final_df)}")

    # STEP 9: Select and reorder final columns
    final_columns = [
        "item_id",
        "unique_identifier",
        "brand_name",
        "title",
        "category",
        "vertical",
        "subCategory",
        "superCategory",
        "date",
        "revenue",
        "price",
        "rating",
        "rating_count",
        "variations_count",
    ]
    final_df = final_df[final_columns]

    # STEP 10: Sort by item_id and date ascending
    print("Sorting by item_id and date...")
    final_df = final_df.sort_values(by=["item_id", "date"], ascending=[True, True]).reset_index(drop=True)

    # STEP 11: Save to CSV
    output_path = "listingdata_final_for_looker.csv"
    print(f"Saving to {output_path}...")
    final_df.to_csv(output_path, index=False)
    print(f"  Saved {len(final_df)} rows to {output_path}")
    print("Done.")


if __name__ == "__main__":
    main()
