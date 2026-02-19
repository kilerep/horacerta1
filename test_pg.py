import psycopg2

HOST = "horacerta-db.c5se68e0q3rl.us-east-2.rds.amazonaws.com"
USER = "postgres"
PASSWORD = "HoraCerta2026Aa"
DBNAME = "postgres"
PORT = 5432

conn = psycopg2.connect(
    host=HOST,
    port=PORT,
    user=USER,
    password=PASSWORD,
    dbname=DBNAME,
)
print("✅ Conectou no RDS PostgreSQL!")
conn.close()
