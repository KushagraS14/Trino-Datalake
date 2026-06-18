# Save as query_user_data.py and run
import duckdb

# Connect to DuckDB
conn = duckdb.connect()

print("=" * 60)
print("USER DATA ANALYTICS")
print("=" * 60)

# Query 1: Basic statistics
print("\n📊 BASIC STATISTICS:")
result = conn.execute("""
    SELECT 
        COUNT(*) as total_records,
        COUNT(DISTINCT gender) as gender_types,
        ROUND(AVG(salary), 2) as average_salary,
        MIN(salary) as min_salary,
        MAX(salary) as max_salary
    FROM '/Users/kushagrasrivastava/Downloads/userdata.parquet'
""").fetchdf()
print(result)

# Query 2: Gender distribution
print("\n📊 GENDER DISTRIBUTION:")
result = conn.execute("""
    SELECT 
        gender,
        COUNT(*) as count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage,
        ROUND(AVG(salary), 2) as avg_salary
    FROM '/Users/kushagrasrivastava/Downloads/userdata.parquet'
    GROUP BY gender
    ORDER BY count DESC
""").fetchdf()
print(result)

# Query 3: Registration trends by month
print("\n📊 REGISTRATION TRENDS (Last 12 months):")
result = conn.execute("""
    SELECT 
        DATE_TRUNC('month', registration_dttm) as registration_month,
        COUNT(*) as new_users,
        ROUND(AVG(salary), 2) as avg_salary
    FROM '/Users/kushagrasrivastava/Downloads/userdata.parquet'
    WHERE registration_dttm IS NOT NULL
    GROUP BY DATE_TRUNC('month', registration_dttm)
    ORDER BY registration_month DESC
    LIMIT 12
""").fetchdf()
print(result)

# Query 4: Salary distribution
print("\n📊 SALARY DISTRIBUTION:")
result = conn.execute("""
    SELECT 
        CASE 
            WHEN salary < 30000 THEN 'Under $30K'
            WHEN salary BETWEEN 30000 AND 49999 THEN '$30K-$49K'
            WHEN salary BETWEEN 50000 AND 74999 THEN '$50K-$74K'
            WHEN salary BETWEEN 75000 AND 99999 THEN '$75K-$99K'
            WHEN salary >= 100000 THEN '$100K+'
            ELSE 'Unknown'
        END as salary_range,
        COUNT(*) as user_count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage,
        gender,
        COUNT(*) as count_by_gender
    FROM '/Users/kushagrasrivastava/Downloads/userdata.parquet'
    GROUP BY salary_range, gender
    ORDER BY MIN(salary), gender
""").fetchdf()
print(result)

# Query 5: Top earners
print("\n📊 TOP 10 HIGHEST SALARIES:")
result = conn.execute("""
    SELECT 
        gender,
        salary,
        registration_dttm
    FROM '/Users/kushagrasrivastava/Downloads/userdata.parquet'
    ORDER BY salary DESC
    LIMIT 10
""").fetchdf()
print(result)

# Query 6: Registration by day of week
print("\n📊 REGISTRATION BY DAY OF WEEK:")
result = conn.execute("""
    SELECT 
        DAYNAME(registration_dttm) as day_of_week,
        COUNT(*) as registrations,
        ROUND(AVG(salary), 2) as avg_salary
    FROM '/Users/kushagrasrivastava/Downloads/userdata.parquet'
    GROUP BY DAYNAME(registration_dttm)
    ORDER BY registrations DESC
""").fetchdf()
print(result)

print("\n✅ All queries completed!")