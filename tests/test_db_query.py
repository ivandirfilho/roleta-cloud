"""Test script to query the database and check the last predictions."""
import sqlite3
import json

# Connect to the database
conn = sqlite3.connect('microservico_previsoes.db')
cursor = conn.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables:", [t[0] for t in tables])

# Query the predictions table(s)
for table_name in [t[0] for t in tables]:
    print(f"\n=== Table: {table_name} ===")
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    print("Columns:", [c[1] for c in columns])
    
    cursor.execute(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT 3")
    rows = cursor.fetchall()
    for row in rows:
        print(f"Row: {row}")
        # Try to parse regiao_vicio if present
        for i, col in enumerate(columns):
            if 'regiao' in col[1].lower():
                try:
                    regiao = json.loads(row[i])
                    print(f"  -> Região parsed: {regiao}")
                    print(f"  -> 14 in região? {14 in regiao}")
                    print(f"  -> 4 in região? {4 in regiao}")
                except:
                    pass

conn.close()
