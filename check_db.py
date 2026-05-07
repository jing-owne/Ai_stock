import sqlite3
conn = sqlite3.connect(r'C:\Users\admin\.workbuddy\workbuddy.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print("Tables:", tables)

for table in tables:
    cursor.execute(f"SELECT * FROM {table} LIMIT 5")
    rows = cursor.fetchall()
    if rows:
        cols = [d[0] for d in cursor.description]
        print(f"\n=== {table} ===")
        print("Columns:", cols)
        for row in rows:
            print(row)

conn.close()
