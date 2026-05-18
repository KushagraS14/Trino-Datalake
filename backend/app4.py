import os
import tempfile
import re
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
import trino
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Import our custom helper scripts
from schema_inference import generate_trino_schema
from backend.minio_uploaderff import upload_to_minio

# Load the secret variables from your .env file into Python's memory
load_dotenv()

app = Flask(__name__)
CORS(app) 

# ── Schema bootstrap ─────────────────────────────────────────────────────────
CATALOG = 'datalake'
SCHEMA  = 'analytic'

# ALLOWED EXTENSIONS
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'json', 'parquet'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_schema_for_trino(schema_string):
    """
    Aggressively cleans column names to be Trino-compatible.
    This fixes the '.1' error by replacing dots with underscores.
    """
    import re
    
    # Split into individual column definitions
    lines = schema_string.split(',\n    ')
    cleaned_lines = []
    
    for line in lines:
        # Split column name and type
        if ' VARCHAR' in line:
            col_part = line.replace(' VARCHAR', '')
            col_name = col_part.strip()
            
            # Clean the column name
            # Replace dots with underscores (fixes "2.1" -> "2_1")
            col_name = col_name.replace('.', '_')
            
            # Remove any other invalid characters
            col_name = re.sub(r'[^a-zA-Z0-9_]', '_', col_name)
            
            # Remove multiple underscores
            col_name = re.sub(r'_+', '_', col_name)
            
            # Remove leading/trailing underscores
            col_name = col_name.strip('_')
            
            # If starts with number, add prefix
            if col_name and col_name[0].isdigit():
                col_name = 'col_' + col_name
            
            # If empty, use generic name
            if not col_name:
                col_name = 'column'
            
            # Rebuild the line
            cleaned_lines.append(f"{col_name} VARCHAR")
        else:
            cleaned_lines.append(line)
    
    return ',\n    '.join(cleaned_lines)

def ensure_schema_exists():
    """Create the analytic schema inside the datalake catalog if it doesn't exist."""
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
        print(f"⚠️  Could not ensure schema (Trino may not be up yet): {e}")

# Verify the .env file exists and loaded correctly
VALID_API_KEY = os.getenv("TRINO_API_KEY")
if not VALID_API_KEY:
    raise ValueError("CRITICAL ERROR: TRINO_API_KEY is missing from the .env file.")

CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])

# You can extend this list later with office or staging IPs.
ALLOWED_IPS = {"127.0.0.1", "::1", "localhost"}

@app.before_request
def limit_remote_addr():
    if request.path == '/query':
        client_ip = request.remote_addr
        if client_ip not in ALLOWED_IPS:
            print(f"🚨 SECURITY ALERT: Blocked unauthorized access from IP: {client_ip}")
            abort(403)  # HTTP 403 Forbidden

# ROUTE 1: THE DASHBOARD QUERY ENGINE
@app.route('/')
def home():
    return "Flask server is running!"

@app.route('/query', methods=['POST'])
def run_query():
    data = request.json
    if not data or 'query' not in data:
        return jsonify({'error': 'No SQL query provided'}), 400
        
    sql_query = data['query'].strip().rstrip(';').strip()
    
    # Security Whitelist: Only allow SELECT and SHOW queries
    if not sql_query.strip().upper().startswith(("SELECT", "SHOW","DESCRIBE", "WITH")):
        return jsonify({'error': 'Security blocked: Only SELECT and SHOW queries are allowed'}), 403

    try:
        # Connect to Trino
        conn = trino.dbapi.connect(
            host='localhost',
            port=8080,
            user='admin',
            catalog=CATALOG,
            schema=SCHEMA
        )
        print("✅ Trino engine started and connected to MinIO")
        cur = conn.cursor()
        cur.execute(sql_query)
        rows = cur.fetchall()
        
        # Extract column headers
        columns = [desc[0] for desc in cur.description] if cur.description else []
        
        return jsonify({
            'columns': columns,
            'rows': rows
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ROUTE 2: THE AUTOMATED INGESTION PIPELINE
@app.route('/ingest', methods=['POST'])
def ingest_csv():
    # 1. Security Check
    api_key = request.headers.get('X-API-KEY')
    print(f"DEBUG - API key received: {'[VALID]' if api_key == VALID_API_KEY else '[INVALID]'}")
    if api_key != VALID_API_KEY:
        abort(401)  # Unauthorized

    # 2. Check if file is in the request
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        # Save file temporarily
        filename = secure_filename(file.filename)
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, filename)
        file.save(temp_file_path)

        try:
            # Get file extension
            file_ext = filename.rsplit('.', 1)[1].lower()
            
            # 3. Infer Schema (different logic based on file type)
            if file_ext == 'csv':
                schema_string, schema_mapping = generate_trino_schema(temp_file_path, file_ext)
                
            elif file_ext == 'xlsx':
    # Simplified Excel parsing
                import pandas as pd
    
    # Force pandas to use openpyxl
            try:
                df = pd.read_excel(temp_file_path, engine='openpyxl')
                print(f"DEBUG - Excel loaded successfully: {df.shape[0]} rows, {df.shape[1]} columns")
            except Exception as e:
                print(f"DEBUG - Error loading Excel: {e}")
                return jsonify({'error': f'Failed to read Excel file: {str(e)}. Try: pip install openpyxl'}), 400
    
    # Convert to CSV
        csv_path = temp_file_path.replace('.xlsx', '.csv')
        df.to_csv(csv_path, index=False)
        schema_string, schema_mapping = generate_trino_schema(csv_path, file_ext)
        temp_file_path = csv_path
            elif file_ext == 'json':
                # Add JSON parsing logic
                import pandas as pd
                df = pd.read_json(temp_file_path)
                csv_path = temp_file_path.replace('.json', '.csv')
                df.to_csv(csv_path, index=False)
                schema_string, schema_mapping = generate_trino_schema(csv_path, file_ext)
                temp_file_path = csv_path
                
            elif file_ext == 'parquet':
                # Add Parquet parsing logic
                import pandas as pd
                df = pd.read_parquet(temp_file_path)
                csv_path = temp_file_path.replace('.parquet', '.csv')
                df.to_csv(csv_path, index=False)
                schema_string, schema_mapping = generate_trino_schema(csv_path, file_ext)
                temp_file_path = csv_path
            
            # IMPORTANT: Clean the schema string before using it
            print(f"DEBUG - Original schema: {schema_string}")
            cleaned_schema_string = clean_schema_for_trino(schema_string)
            print(f"DEBUG - Cleaned schema: {cleaned_schema_string}")
            
            # 4. Clean Table Name & Upload to MinIO
            table_name = re.sub(r'[^a-z0-9_]', '_', filename.split('.')[0].lower())
            
            # Upload to MinIO
            s3_folder_path = upload_to_minio(temp_file_path, table_name)

            # 5. Ensure schema exists, then connect to Trino
            ensure_schema_exists()
            conn = trino.dbapi.connect(
                host='localhost',
                port=8080,
                user='admin',
                catalog=CATALOG,
                schema=SCHEMA
            )
            cur = conn.cursor()

            # 6. Create Table with cleaned schema
            table_format = 'CSV'
            skip_header = 1 if file_ext == 'csv' else 0
                
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS datalake.analytic.{table_name} (
                {cleaned_schema_string}
            )
            WITH (
                format = '{table_format}',
                external_location = '{s3_folder_path}',
                skip_header_line_count = {skip_header}
            )
            """
            
            print(f"DEBUG - Create table query: {create_table_query}")
            
            cur.execute(create_table_query)
            cur.fetchall()
            
            # Clean up the temporary file(s)
            os.remove(temp_file_path)
            if file_ext != 'csv' and os.path.exists(temp_file_path.replace(f'.{file_ext}', '.csv')):
                os.remove(temp_file_path.replace(f'.{file_ext}', '.csv'))

            # Return success with schema_mapping
            return jsonify({
                'message': f'Successfully ingested {filename} into table {table_name}',
                'table': table_name,
                'location': s3_folder_path,
                'schema_mapping': schema_mapping  
            }), 200

        except Exception as e:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Invalid file format. Only CSV, XLSX, JSON, Parquet allowed.'}), 400

# SERVER START
if __name__ == '__main__':
    ensure_schema_exists()   # Bootstrap schema on startup
    app.run(debug=True, port=5001)