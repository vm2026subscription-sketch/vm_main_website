"""
Excel upload parsing and MongoDB insertion service.
"""
import io

try:
    import pandas as pd
except ImportError:
    pd = None


def convert_excel_to_records(uploaded_file):
    if pd is None:
        raise RuntimeError("pandas is not installed. Install requirements to process Excel uploads.")

    excel_bytes = uploaded_file.read()
    if not excel_bytes:
        raise ValueError("The uploaded file is empty.")

    workbook = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=None)
    if not workbook:
        raise ValueError("No sheets found in the uploaded Excel file.")

    records = []
    for sheet_name, dataframe in workbook.items():
        cleaned_dataframe = dataframe.where(pd.notnull(dataframe), None)
        for row_index, row in cleaned_dataframe.iterrows():
            payload = {}
            for column_name, value in row.items():
                normalized_column = str(column_name).strip()
                if not normalized_column:
                    continue
                payload[normalized_column] = value
            if not payload:
                continue
            records.append({
                "file_name": uploaded_file.filename,
                "sheet_name": str(sheet_name),
                "row_number": int(row_index) + 2,
                "payload": payload,
            })

    if not records:
        raise ValueError("The uploaded Excel file has no data rows to store.")

    return records


def insert_records_via_mongo(collection_name, records, batch_size=500):
    """Insert Excel records into a MongoDB collection."""
    from app.utils.mongo import get_upload_collection
    from datetime import datetime, timezone

    col = get_upload_collection(collection_name)
    now = datetime.now(timezone.utc)

    # Add uploaded_at timestamp to each record
    docs = []
    for r in records:
        doc = dict(r)
        doc["uploaded_at"] = now
        docs.append(doc)

    inserted = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        col.insert_many(batch)
        inserted += len(batch)

    return inserted
