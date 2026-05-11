from dotenv import load_dotenv
import os
import sys

# load env from project
load_dotenv()
# make sure project root is on sys.path so we can import app
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import ensure_upload_table_exists, insert_records_via_postgres, get_postgres_connection_url

conn_url = get_postgres_connection_url()
if not conn_url:
    print('NO_CONNECTION_URL')
    sys.exit(2)

table_name = 'excel_test'

records = [
    {
        'file_name': 'test_upload.xlsx',
        'sheet_name': 'Sheet1',
        'row_number': 2,
        'payload': {'college_name': 'Test College', 'city': 'Pune', 'state': 'Maharashtra'}
    },
    {
        'file_name': 'test_upload.xlsx',
        'sheet_name': 'Sheet1',
        'row_number': 3,
        'payload': {'college_name': 'Another College', 'city': 'Mumbai', 'state': 'Maharashtra'}
    },
]

print('Using connection:', conn_url[:60] + '...' if conn_url else None)
try:
    ensure_upload_table_exists(conn_url, table_name)
    inserted = insert_records_via_postgres(conn_url, table_name, records)
    print('INSERTED_ROWS', inserted)
except Exception as e:
    print('ERROR', e)
    raise
