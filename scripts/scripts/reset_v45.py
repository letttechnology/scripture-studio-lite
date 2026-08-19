"""
One-time fix: drop audit tables created with wrong 'rev' PK column,
and remove V45 from flyway_schema_history so it re-runs with corrected SQL.
Run once, then restart admin service.
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="interlinear_bible_dev",
    user="postgres", password="letttech"
)
conn.autocommit = False
cur = conn.cursor()

for table in ["lexeme_meaning_aud", "contextual_gloss_aud", "cluster_gloss_rule_aud", "revinfo"]:
    cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    print(f"Dropped: {table}")

cur.execute("DROP SEQUENCE IF EXISTS revinfo_seq")
print("Dropped sequence: revinfo_seq")

cur.execute("DELETE FROM flyway_schema_history WHERE version = '45'")
print(f"Removed {cur.rowcount} V45 row(s) from flyway_schema_history")

conn.commit()
cur.close()
conn.close()
print("Done. Restart admin service.")
