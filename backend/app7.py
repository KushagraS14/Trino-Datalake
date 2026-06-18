import os
import tempfile
import re
import csv
import secrets
import bcrypt
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, abort, session
from flask_cors import CORS
import trino
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import psycopg2  # Fixed: was 'pyscopg2', now correct 'psycopg2'
from psycopg2.extras import RealDictCursor  # Fixed: was 'pyscopg2.extras'

# Import custom helpers (with error handling)
try:
    from schema_inference import generate_trino_schema
except ImportError:
    generate_trino_schema = None
    print("⚠️ schema_inference module not found")

try:
    from minio_uploader import upload_to_minio
except ImportError:
    upload_to_minio = None
    print("⚠️ minio_uploader module not found")

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

# CORS configuration
CORS(app, origins=[
    "http://localhost:5173", 
    "http://127.0.0.1:5173", 
    "http://localhost:3000",
    "http://localhost:5000",
    "http://localhost:5001"
], supports_credentials=True)

# Configuration
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'json', 'parquet'}
CATALOG = 'datalake'
SCHEMA = 'analytic'
VALID_API_KEY = os.getenv("TRINO_API_KEY", "trino-secure-key-2026")

# Database connection
def get_db_connection():
    try:
        return psycopg2.connect(
            host='localhost',
            database='tcai_data_lake',
            user='kushagrasrivastava',
            password='',
            port=5432
        )
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None

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

# ==================== AUTHENTICATION ENDPOINTS ====================

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        remember_me = data.get('rememberMe', False)
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute('SELECT id, email, password_hash, full_name, role FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        cur.close()
        
        if not user:
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Verify password
        if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            # Generate session token
            session_token = secrets.token_hex(32)
            
            # Set session expiry
            if remember_me:
                expires = datetime.now() + timedelta(days=30)
            else:
                expires = datetime.now() + timedelta(hours=24)
            
            # Store session in database
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO sessions (user_id, session_token, expires_at) VALUES (%s, %s, %s)',
                (user['id'], session_token, expires)
            )
            conn.commit()
            cur.close()
            conn.close()
            
            return jsonify({
                'success': True,
                'sessionToken': session_token,
                'user': {
                    'id': user['id'],
                    'email': user['email'],
                    'full_name': user['full_name'],
                    'role': user['role']
                },
                'expiresAt': expires.isoformat()
            })
        else:
            return jsonify({'error': 'Invalid email or password'}), 401
            
    except Exception as e:
        print(f"❌ Login error: {e}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/current-user', methods=['GET'])
def get_current_user():
    session_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not session_token:
        return jsonify({'error': 'No session token'}), 401
    
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500
            
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check session
        cur.execute('SELECT user_id, expires_at FROM sessions WHERE session_token = %s', (session_token,))
        session_data = cur.fetchone()
        
        if not session_data:
            return jsonify({'error': 'Invalid session'}), 401
        
        # Check if session expired
        if datetime.now() > session_data['expires_at']:
            cur.execute('DELETE FROM sessions WHERE session_token = %s', (session_token,))
            conn.commit()
            return jsonify({'error': 'Session expired'}), 401
        
        # Get user data
        cur.execute('SELECT id, email, full_name, role FROM users WHERE id = %s', (session_data['user_id'],))
        user = cur.fetchone()
        
        cur.close()
        conn.close()
        
        return jsonify({'user': user})
        
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if session_token:
        try:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute('DELETE FROM sessions WHERE session_token = %s', (session_token,))
                conn.commit()
                cur.close()
                conn.close()
        except Exception as e:
            print(f"❌ Logout error: {e}")
    
    return jsonify({'success': True})

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy', 
        'message': 'Backend is running',
        'timestamp': datetime.now().isoformat()
    }), 200

# ==================== FILE UPLOAD ENDPOINTS ====================

@app.route('/upload', methods=['POST'])
def simple_upload():
    """Simple upload endpoint for frontend"""
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
                
                # Create CSV
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='') as tmp_file:
                    csv_path = tmp_file.name
                    writer = csv.writer(tmp_file)
                    writer.writerow(df.columns.tolist())
                    for _, row in df.iterrows():
                        writer.writerow(row.tolist())
                
                # Upload to MinIO if available
                if upload_to_minio:
                    s3_folder_path = upload_to_minio(csv_path, table_name)
                else:
                    s3_folder_path = f"/tmp/{table_name}"
                
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
            
            if upload_to_minio:
                s3_folder_path = upload_to_minio(csv_path, table_name)
            else:
                s3_folder_path = f"/tmp/{table_name}"
            
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
        return jsonify({'error': str(e)}), 500

# ==================== QUERY ENDPOINTS ====================

@app.route('/query', methods=['POST'])
def run_query():
    data = request.json
    if not data or 'query' not in data:
        return jsonify({'error': 'No SQL query provided'}), 400
    
    sql_query = data['query'].strip().rstrip(';').strip()
    query_upper = sql_query.upper()
    
    # Allowed commands
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
        print(f"❌ Query error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/ingest', methods=['POST'])
def ingest_file():
    """Legacy ingest endpoint with API key"""
    print("=" * 50)
    print("✅ INGEST ROUTE WAS CALLED!")
    
    api_key = request.headers.get('X-API-KEY')
    if api_key != VALID_API_KEY:
        abort(401)
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file format'}), 400
    
    # Similar processing as above
    return jsonify({'message': 'Ingest endpoint working'}), 200

@app.route('/')
def home():
    return jsonify({
        'message': 'TCAI Data Lake API',
        'version': '1.0',
        'endpoints': [
            '/api/login',
            '/api/health',
            '/upload',
            '/query',
            '/api/current-user',
            '/api/logout'
        ]
    })

if __name__ == '__main__':
    ensure_schema_exists()
    print("🚀 Starting Flask server on http://localhost:5001")
    print("📧 Login with: admin@tcai.com")
    print("🔑 Password: admin123")
    app.run(debug=True, host='0.0.0.0', port=5001)