import duckdb

# Connect to DuckDB
conn = duckdb.connect()

# Run the query
result = conn.execute("""
    SELECT 
        country,
        COUNT(*) as user_count,
        AVG(age) as avg_age
    FROM '/Users/kushagrasrivastava/Downloads/userdata.parquet'
    GROUP BY country
    ORDER BY user_count DESC
    LIMIT 10
""").fetchdf()

print(result)
