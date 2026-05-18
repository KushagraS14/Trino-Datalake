import pandas as pd
import re
import trino

conn = trino.dbapi.connect(
    host='localhost',
    port=8080,
    user='test_user',
    catalog='datalake',
    schema='analytic',
    http_scheme='http'
)

def clean_column_name(col_name):
    """
    Aggressively cleans column names to be Trino-compatible.
    Trino rules:
    - Must start with a letter or underscore
    - Can only contain letters, numbers, underscores
    - No dots, spaces, or special characters
    """
    # Convert to string and strip
    clean_name = str(col_name).strip()
    
    # Replace ALL non-alphanumeric characters (except spaces) with underscores
    # This includes dots, dashes, slashes, etc.
    clean_name = re.sub(r'[^a-zA-Z0-9\s]', '_', clean_name)
    
    # Replace spaces with underscores
    clean_name = clean_name.replace(' ', '_')
    
    # Convert to lowercase for consistency
    clean_name = clean_name.lower()
    
    # Remove multiple consecutive underscores
    clean_name = re.sub(r'_+', '_', clean_name)
    
    # Remove leading/trailing underscores
    clean_name = clean_name.strip('_')
    
    # If empty after cleaning, give a default name
    if not clean_name:
        clean_name = "column"
    
    # If starts with a number, add 'col_' prefix
    if clean_name and clean_name[0].isdigit():
        # Also remove any remaining dots from numbers
        clean_name = re.sub(r'(\d+)\.(\d+)', r'\1_\2', clean_name)
        clean_name = "col_" + clean_name
    
    # Final safety check - ensure no dots remain
    clean_name = clean_name.replace('.', '_')
    
    return clean_name

def generate_trino_schema(file_path, file_ext=None):
    """
    Reads the file based on its extension, maps every column to VARCHAR,
    and returns a mapping dictionary of the original names to cleaned names.
    """
    # Remove the dot from file_ext if present
    if file_ext and file_ext.startswith('.'):
        file_ext = file_ext[1:]
    
    # Default to csv if no extension provided
    if not file_ext:
        file_ext = 'csv'
    
    # Read the file based on extension
    if file_ext == 'csv':
        df = pd.read_csv(file_path)
    elif file_ext == 'parquet':
        df = pd.read_parquet(file_path)
    elif file_ext == 'xlsx':
        df = pd.read_excel(file_path)
    elif file_ext == 'json':
        df = pd.read_json(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_ext}")
    
    schema_parts = []
    mapping = {}
    
    print(f"DEBUG - Original columns: {list(df.columns)}")  # Debug output
    
    for col in df.columns:
        clean_col = clean_column_name(col)
        
        print(f"DEBUG - Cleaning: '{col}' -> '{clean_col}'")  # Debug output
        
        # Store the Original -> Cleaned relationship
        mapping[col] = clean_col
        
        # Use VARCHAR for all columns to avoid type issues
        sql_type = 'VARCHAR'
        
        # Don't use quotes - let Trino handle standard identifiers
        schema_parts.append(f"{clean_col} {sql_type}")
        
    final_sql_schema = ",\n    ".join(schema_parts)
    
    print(f"DEBUG - Final schema: {final_sql_schema}")  # Debug output
    
    return final_sql_schema, mapping

if __name__ == "__main__":
    print("Testing Schema Guesser...")
    try:
        schema_string, schema_mapping = generate_trino_schema("hr_data_cleaned.csv", "csv")
        
        print("--- Generated SQL Schema ---")
        print(schema_string)
        print("\n--- Column Mapping Dictionary ---")
        print(schema_mapping)
    except Exception as e:
        print(f"Error: {e}")