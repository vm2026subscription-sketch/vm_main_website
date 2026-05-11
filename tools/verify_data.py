from dotenv import load_dotenv
import os
import sys

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import get_postgres_connection_url, connect
import psycopg2.extras

conn_url = get_postgres_connection_url()
with connect(conn_url) as conn:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT payload FROM entrance_exams LIMIT 3")
        rows = cur.fetchall()
        for r in rows:
            p = r["payload"]
            print(f"exam_name={p.get('exam_name')}, full_form={str(p.get('full_form', 'N/A'))[:40]}, level={p.get('level')}, college={p.get('college_name')}")
