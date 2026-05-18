import os
import pandas as pd
import tempfile
from minio import Minio
#!/usr/bin/env python3
import sys
import subprocess
import os
import sys

print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")

try:
    import openpyxl
    print(f"✅ openpyxl version: {openpyxl.__version__}")
except ImportError as e:
    print(f"❌ openpyxl import failed: {e}")
    print("Install with: pip install openpyxl")
    sys.exit(1)

try:
    from minio import Minio
    print("✅ minio imported successfully")
except ImportError as e:
    print(f"❌ minio import failed: {e}")
    sys.exit(1)

import pandas as pd
import tempfile

# ADD THIS MINIO CONNECTION TEST HERE
print("\n--- Testing MinIO Connection ---")
try:
    test_client = Minio(
        "localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False
    )
    
    # Test the connection by listing buckets
    buckets = test_client.list_buckets()
    print(f"✅ Successfully connected to MinIO!")
    print(f"📦 Found {len(buckets)} bucket(s): {[b.name for b in buckets]}")
    
    # Check if 'datalake' bucket exists
    bucket_name = "datalake"
    if test_client.bucket_exists(bucket_name):
        print(f"✅ Bucket '{bucket_name}' exists")
    else:
        print(f"⚠️  Bucket '{bucket_name}' does not exist yet (will be created)")
        
except Exception as e:
    print(f"❌ Failed to connect to MinIO: {e}")
    print("\nPossible fixes:")
    print("1. Is MinIO running? Run: docker ps | grep minio")
    print("2. Try using 'minio:9000' instead of 'localhost:9000'")
    print("3. Try using 'host.docker.internal:9000'")
    sys.exit(1)

def test_minio_connection():
    print("=" * 50)
    print("Testing MinIO Connection")
    print("=" * 50)
    
    # Test 1: Check Python environment
    print(f"\n1. Python: {sys.executable}")
    
    # Test 2: Check imports
    print("\n2. Checking imports...")
    try:
        from minio import Minio
        print("   ✅ Minio imported")
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False
    
    # Test 3: Try localhost connection
    print("\n3. Testing localhost:9000...")
    try:
        client = Minio(
            "localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            secure=False
        )
        buckets = client.list_buckets()
        print(f"   ✅ Connected! Buckets: {[b.name for b in buckets]}")
        return True
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        
        # Test 4: Check if port is listening
        print("\n4. Checking if port 9000 is listening...")
        result = subprocess.run(["lsof", "-i", ":9000"], capture_output=True, text=True)
        if result.stdout:
            print(f"   ✅ Port 9000 is in use:\n{result.stdout}")
        else:
            print("   ❌ Port 9000 is not listening. Is MinIO running?")
        
        return False

if __name__ == "__main__":
    test_minio_connection()

def upload_to_minio(file_path, table_name):
    """
    Upload file to MinIO - Handles Excel, CSV, JSON, Parquet
    Converts everything to CSV for consistent Trino querying
    """
    
    # Connect to MinIO API
    client = Minio(
        "localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False
    )

    # TRINO VIP BUCKET (Matches your catalog name exactly)
    bucket_name = "datalake" 

    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)

    # Check if file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Get file extension
    file_ext = os.path.splitext(file_path)[1].lower()
    
    # Convert to DataFrame based on file type
    print(f"Reading {file_ext} file: {file_path}...")
    
    try:    
        if file_ext == '.csv':
            # Direct CSV read
            df = pd.read_csv(file_path)
            print(f"✅ Loaded CSV: {len(df)} rows")
            
        elif file_ext == '.xlsx':
            print("📊 Reading Excel file with openpyxl engine...")
            # Read with proper headers
            df = pd.read_excel(
                file_path, 
                engine='openpyxl',
                header=0,  # First row as headers
                dtype=str  # Read all as string to preserve data
            )
            print(f"✅ Loaded Excel: {len(df)} rows, {len(df.columns)} columns")
            print(f"📊 Columns: {list(df.columns)}")
            
        elif file_ext == '.xls':
            # For older Excel files
            print("📊 Reading legacy Excel file with xlrd engine...")
            df = pd.read_excel(file_path, engine='xlrd')
            print(f"✅ Loaded Excel: {len(df)} rows")
            
        elif file_ext == '.json':
            df = pd.read_json(file_path)
            print(f"✅ Loaded JSON: {len(df)} rows")
            
        elif file_ext == '.parquet':
            df = pd.read_parquet(file_path)
            print(f"✅ Loaded Parquet: {len(df)} rows")
            
        else:
            raise ValueError(f"Unsupported file type: {file_ext}. Supported: .csv, .xlsx, .xls, .json, .parquet")
        
        # Remove any completely empty rows
        original_rows = len(df)
        df = df.dropna(how='all')
        if len(df) < original_rows:
            print(f"🗑️ Removed {original_rows - len(df)} empty rows")
        
        # Create a temporary CSV file for MinIO upload
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='') as tmp_file:
            temp_csv_path = tmp_file.name
            df.to_csv(temp_csv_path, index=False, encoding='utf-8')
            print(f"📝 Converted to CSV: {temp_csv_path}")
        
        # Verify CSV has correct number of rows
        with open(temp_csv_path, 'r') as f:
            csv_row_count = sum(1 for line in f if line.strip())
            expected_rows = len(df) + 1  # +1 for header
            print(f"📊 CSV verification: {csv_row_count} rows (expected {expected_rows})")
            
            if csv_row_count != expected_rows:
                print(f"⚠️ Warning: CSV has {csv_row_count - expected_rows} extra lines")
        
        # Upload to MinIO
        object_name = f"{table_name}/data.csv"
        print(f"☁️ Uploading to bucket '{bucket_name}' as '{object_name}'...")
        client.fput_object(bucket_name, object_name, temp_csv_path)
        print(f"✅ Upload complete!")
        
        # Clean up temp file
        os.unlink(temp_csv_path)
        
    except pd.errors.EmptyDataError:
        raise Exception(f"File is empty: {file_path}")
    except pd.errors.ParserError as e:
        raise Exception(f"Error parsing file {file_path}: {e}")
    except Exception as e:
        print(f"❌ Error processing file: {e}")
        raise
    
    # Return the exact folder path Trino needs
    s3_folder_path = f"s3a://{bucket_name}/{table_name}/"
    print(f"🔗 Trino path: {s3_folder_path}")
    
    return s3_folder_path

# Test function when run directly
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 2:
        file_path = sys.argv[1]
        table_name = sys.argv[2]
        
        # Debug info
        print(f"Attempting to upload file at: {file_path}")
        print(f"File exists: {os.path.exists(file_path)}")
        if os.path.exists(file_path):
            print(f"File size: {os.path.getsize(file_path)} bytes")
        
        # Call upload function
        result = upload_to_minio(file_path, table_name)
        print(f"\n✅ Success! Result: {result}")
    else:
        print("Usage: python minio_uploader.py <file_path> <table_name>")
        print("Example: python minio_uploader.py data.xlsx my_table")