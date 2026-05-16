from billing.database import get_connection
conn = get_connection()
rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [r[0] for r in rows])
cols = conn.execute("PRAGMA table_info(recharge_requests)").fetchall()
print("recharge_requests columns:", [c[1] for c in cols])
conn.close()
