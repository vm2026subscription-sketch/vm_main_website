from dotenv import load_dotenv
import os
import sys

load_dotenv()
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import convert_excel_to_records, insert_records_via_postgres, get_postgres_connection_url

EXCEL_PATH = os.path.join(PROJECT_ROOT, 'data', 'all_in_one_clean_v2.xlsx')
TABLE_NAME = 'entrance_exams'

if not os.path.exists(EXCEL_PATH):
    print('MISSING_FILE', EXCEL_PATH)
    sys.exit(2)

print('Reading', EXCEL_PATH)
with open(EXCEL_PATH, 'rb') as f:
    class UploadedFileLike:
        def __init__(self, filename, fh):
            self.filename = filename
            self._fh = fh
        def read(self):
            self._fh.seek(0)
            return self._fh.read()

    uploaded = UploadedFileLike(os.path.basename(EXCEL_PATH), f)
    try:
        records = convert_excel_to_records(uploaded)
    except Exception as e:
        print('CONVERT_ERROR', e)
        raise

print('Found records:', len(records))
conn_url = get_postgres_connection_url()
if not conn_url:
    print('NO_POSTGRES_URL')
    sys.exit(2)

print('Inserting into', TABLE_NAME)
try:
    # sanitize records to replace NaN/numpy types with JSON-safe Python types
    import pandas as _pd
    import numpy as _np
    import math as _math

    def sanitize(obj):
        if isinstance(obj, dict):
            return {k: sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [sanitize(v) for v in obj]
        # numpy scalars -> native Python
        if isinstance(obj, _np.generic):
            try:
                return obj.item()
            except Exception:
                return str(obj)
        try:
            if _pd.isna(obj):
                return None
        except Exception:
            pass
        if isinstance(obj, float):
            if _math.isnan(obj) or _math.isinf(obj):
                return None
        return obj

    for r in records:
        r['payload'] = sanitize(r.get('payload', {}))

    # ensure table exists then insert
    from app import ensure_upload_table_exists
    ensure_upload_table_exists(conn_url, TABLE_NAME)
    inserted = insert_records_via_postgres(conn_url, TABLE_NAME, records)
    print('INSERTED', inserted)
except Exception as e:
    print('INSERT_ERROR', e)
    raise
