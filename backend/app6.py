import os
import tempfile
import re
import csv
import pandas as pd
from io import BytesIO
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
import trino
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Import custom helpers
from schema_inference import generate_trino_schema
from minio_uploader import upload_to_minio
# Add to your Flask app.py
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host='localhost',
        database='tcai_data_lake',
        user='kushagrasrivastava',
        password=''
    )

# Login endpoint for Flask
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute('SELECT * FROM users WHERE email = %s', (email,))
    user = cur.fetchone()
    
    cur.close()
    conn.close()
    
    if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        # Generate session token
        session_token = secrets.token_hex(32)
        return jsonify({'success': True, 'sessionToken': session_token, 'user': user})
    else:
        return jsonify({'error': 'Invalid credentials'}), 401
load_dotenv()

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"])
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'json', 'parquet'}
CATALOG = 'datalake'
SCHEMA = 'analytic'
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'json', 'parquet'}

VALID_API_KEY = os.getenv("TRINO_API_KEY")
if not VALID_API_KEY:
    raise ValueError("CRITICAL: TRINO_API_KEY missing from .env")


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def ensure_schema_exists():
    try:
        conn = trino.dbapi.connect(
            host='localhost', port=8080, user='admin',
            catalog=CATALOG, schema=SCHEMA
        )
        cur = conn.cursor()
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
        cur.fetchall()
        print(f"✅ Schema {CATALOG}.{SCHEMA} is ready.")
    except Exception as e:
        print(f"⚠️ Could not ensure schema: {e}")


def clean_dataframe(df):
    """Clean DataFrame by removing newlines and extra spaces"""
    def clean_text(x):
        if pd.isna(x):
            return ''
        if isinstance(x, str):
            x = x.replace('\n', ' ').replace('\r', ' ')
            x = re.sub(r'\s+', ' ', x)
            return x.strip()
        return str(x) if x is not None else ''
    
    for col in df.columns:
        df[col] = df[col].apply(clean_text)
    return df


@app.route('/')
def home():
    return "Flask server is running!"


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for frontend"""
    return jsonify({'status': 'healthy', 'message': 'Backend is running'}), 200


@app.route('/upload', methods=['POST'])
def simple_upload():
    """Simple upload endpoint for frontend - no API key required"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file format. Only CSV, XLSX, JSON, Parquet allowed.'}), 400
        
        # Get table name
        table_name = request.form.get('table_name')
        if not table_name:
            table_name = re.sub(r'[^a-z0-9_]', '_', file.filename.split('.')[0].lower())
        
        # Read file as bytes
        filename = secure_filename(file.filename)
        file_bytes = file.read()
        
        print(f"📁 File: {filename}")
        print(f"📏 Bytes received: {len(file_bytes)} bytes")
        
        if len(file_bytes) == 0:
            return jsonify({'error': 'File is empty (0 bytes)'}), 400
        
        file_ext = filename.rsplit('.', 1)[1].lower()
        
        # Handle Excel files
        if file_ext == 'xlsx':
            print(f"📊 Reading Excel from memory...")
            
            try:
                df = pd.read_excel(
                    BytesIO(file_bytes),
                    engine='openpyxl',
                    header=0,
                    dtype=str
                )
                
                print(f"✅ Loaded {len(df)} rows, {len(df.columns)} columns")
                
                # Clean the data
                df = clean_dataframe(df)
                print(f"✅ Cleaned {len(df)} rows")
                
                # Create CSV using csv.writer to avoid duplication
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='') as tmp_file:
                    csv_path = tmp_file.name
                    writer = csv.writer(tmp_file)
                    writer.writerow(df.columns.tolist())
                    for _, row in df.iterrows():
                        writer.writerow(row.tolist())
                
                print(f"📝 Created CSV: {csv_path}")
                
                # Upload to MinIO
                s3_folder_path = upload_to_minio(csv_path, table_name)
                
                # Clean up
                os.unlink(csv_path)
                
                return jsonify({
                    'success': True,
                    'message': f'Successfully uploaded {filename}',
                    'table_name': table_name,
                    'trino_path': s3_folder_path,
                    'rows': len(df),
                    'columns': list(df.columns)
                }), 200
                
            except Exception as e:
                print(f"❌ Excel reading error: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'Failed to read Excel: {str(e)}'}), 400
        
        # Handle CSV files
        elif file_ext == 'csv':
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as tmp_file:
                tmp_file.write(file_bytes)
                csv_path = tmp_file.name
            
            s3_folder_path = upload_to_minio(csv_path, table_name)
            os.unlink(csv_path)
            
            df = pd.read_csv(BytesIO(file_bytes))
            
            return jsonify({
                'success': True,
                'message': f'Successfully uploaded {filename}',
                'table_name': table_name,
                'trino_path': s3_folder_path,
                'rows': len(df),
                'columns': list(df.columns)
            }), 200
        
        else:
            return jsonify({'error': f'Unsupported file type: {file_ext}'}), 400
                
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/query', methods=['POST'])
def run_query():
    data = request.json
    if not data or 'query' not in data:
        return jsonify({'error': 'No SQL query provided'}), 400
    
    sql_query = data['query'].strip().rstrip(';').strip()
    query_upper = sql_query.upper()
    
    # Add 'CREATE' to the allowed commands
    if not query_upper.startswith(("SELECT", "SHOW", "DESCRIBE", "WITH", "INSERT", "CREATE")):
        return jsonify({'error': 'Only SELECT, SHOW, DESCRIBE, INSERT, CREATE, and WITH queries are allowed'}), 403

    try:
        conn = trino.dbapi.connect(
            host='localhost', port=8080, user='admin',
            catalog=CATALOG, schema=SCHEMA
        )
        cur = conn.cursor()
        cur.execute(sql_query)
        
        # Handle CREATE TABLE operations
        if query_upper.startswith("CREATE"):
            conn.commit()
            return jsonify({
                'success': True,
                'message': 'CREATE TABLE successful',
                'table_created': True
            }), 200
        
        # Handle INSERT operations
        if query_upper.startswith("INSERT"):
            conn.commit()
            return jsonify({
                'success': True,
                'message': 'INSERT successful',
                'rows_affected': cur.rowcount
            }), 200
        
        # Handle SELECT and other read-only queries
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description] if cur.description else []
        return jsonify({'columns': columns, 'rows': rows}), 200
        
    except Exception as e:
        print(f"Query error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/ingest', methods=['POST'])
def ingest_file():
    print("=" * 50)
    print("✅ INGEST ROUTE WAS CALLED!")
    print(f"File in request: {request.files.get('file')}")
    print(f"Filename: {request.files.get('file').filename if request.files.get('file') else 'No file'}")
    print("=" * 50)
    content_type = request.headers.get('Content-Type', '')
    filename = request.files.get('file').filename if request.files.get('file') else ''
    
    # Check if it's an Excel file by extension, not by content
    if filename.endswith(('.xlsx', '.xls')):
        print(f"📊 Excel file detected: {filename}")
        # Force treat as Excel, not zip
    
    api_key = request.headers.get('X-API-KEY')
    if api_key != VALID_API_KEY:
        abort(401)
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file format. Only CSV, XLSX, JSON, Parquet allowed.'}), 400
    
    filename = secure_filename(file.filename)
    temp_dir = tempfile.gettempdir()
    temp_file_path = os.path.join(temp_dir, filename)
    file.save(temp_file_path)
    
    try:
        file_ext = filename.rsplit('.', 1)[1].lower()
        
        if file_ext == 'csv':
            schema_string, schema_mapping = generate_trino_schema(temp_file_path, file_ext)
        
        elif file_ext == 'xlsx':
            import pandas as pd
            # Read Excel
            file_bytes = file.read()
            df = pd.read_excel(
                BytesIO(file_bytes),
                engine='openpyxl',
                header=0,
                dtype=str,
                nrows=4000
            )
            
            # Clean the data
            df = clean_dataframe(df)
            print(f"✅ Loaded and cleaned {len(df)} rows, {len(df.columns)} columns")
            
            # Create CSV
            csv_path = temp_file_path.replace('.xlsx', '.csv')
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(df.columns.tolist())
                for _, row in df.iterrows():
                    writer.writerow(row.tolist())
            
            temp_file_path = csv_path
            schema_string, schema_mapping = generate_trino_schema(csv_path, 'csv')
        
        elif file_ext == 'json':
            import pandas as pd
            df = pd.read_json(temp_file_path)
            csv_path = temp_file_path.replace('.json', '.csv')
            df.to_csv(csv_path, index=False)
            schema_string, schema_mapping = generate_trino_schema(csv_path, 'csv')
            temp_file_path = csv_path
        
        elif file_ext == 'parquet':
            # FIXED: Removed duplicate code and fixed indentation
            try:
                # Try reading with pyarrow engine first
                import pandas as pd
                df = pd.read_parquet(temp_file_path, engine='pyarrow')
                print(f"✅ Read Parquet with pyarrow: {len(df)} rows")
            except ImportError:
                try:
                    # Fall back to fastparquet if pyarrow not available
                    df = pd.read_parquet(temp_file_path, engine='fastparquet')
                    print(f"✅ Read Parquet with fastparquet: {len(df)} rows")
                except Exception as e:
                    return jsonify({'error': f'Failed to read Parquet: {str(e)}. Install pyarrow or fastparquet.'}), 400
            except Exception as e:
                # Check if it's actually a Parquet file
                return jsonify({'error': f'Invalid Parquet file: {str(e)}. Make sure this is a valid Parquet file.'}), 400
            
            # Convert to CSV
            csv_path = temp_file_path.replace('.parquet', '.csv')
            df.to_csv(csv_path, index=False)
            schema_string, schema_mapping = generate_trino_schema(csv_path, 'csv')
            temp_file_path = csv_path
            print(f"✅ Converted Parquet to CSV: {csv_path}")
        
        # Clean column names for Trino
        schema_string = re.sub(r'\.', '_', schema_string)
        schema_string = re.sub(r'[^a-zA-Z0-9_,\n\s]', '_', schema_string)
        
        # Create table name
        table_name = re.sub(r'[^a-z0-9_]', '_', filename.split('.')[0].lower())
        
        # Upload to MinIO
        s3_folder_path = upload_to_minio(temp_file_path, table_name)
        
        # Connect to Trino
        ensure_schema_exists()
        conn = trino.dbapi.connect(
            host='localhost', port=8080, user='admin',
            catalog=CATALOG, schema=SCHEMA
        )
        cur = conn.cursor()
        
        # Create table
        skip_header = 1 if file_ext == 'csv' else 0
        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.{table_name} (
            {schema_string}
        )
        WITH (
            format = 'CSV',
            external_location = '{s3_folder_path}',
            skip_header_line_count = {skip_header}
        )
        """
        
        print(f"CREATE QUERY: {create_table_query}")
        cur.execute(create_table_query)
        cur.fetchall()
        
        # Cleanup
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        
        return jsonify({
            'message': f'Successfully ingested {filename}',
            'table': table_name,
            'schema_mapping': schema_mapping
        }), 200
        
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    ensure_schema_exists()
    app.run(debug=True, host='0.0.0.0', port=5001)