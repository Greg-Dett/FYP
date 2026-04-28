import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from config import settings

@contextmanager
#context manager so connection is always closed and transactions are never left open
def getConnection():
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback() #roll back on any error so we dont leave partial writes
        raise
    finally:
        conn.close()

#used for running the schema file on startup
def runSqlFile(path):
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    with getConnection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)

#RealDictCursor means rows come back as dicts rather than tuples, easier to work with
def GetAll(query, params=()):
    with getConnection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return list(cur.fetchall())

#for inserts/updates where we dont need rows back
def execute(query, params):
    with getConnection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
