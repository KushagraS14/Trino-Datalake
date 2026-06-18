// src/services/api.js
const API_BASE_URL = 'http://localhost:5001';

export const runQuery = async (sqlQuery) => {
  try {
    const response = await fetch(`${API_BASE_URL}/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sqlQuery })
    });
    
    const data = await response.json();
    
    // Check if it's an INSERT response (has success and rows_affected)
    if (data.success !== undefined) {
      console.log(`INSERT successful: ${data.rows_affected} rows affected`);
      return { type: 'insert', message: data.message, rowsAffected: data.rows_affected };
    }
    
    // It's a SELECT response (has columns and rows)
    if (data.columns && data.rows) {
      return { type: 'select', columns: data.columns, rows: data.rows };
    }
    
    // Handle error
    if (data.error) {
      throw new Error(data.error);
    }
    
    return data;
  } catch (error) {
    console.error('Query error:', error);
    throw error;
  }
};

// Optional: Add file upload function
export const uploadFile = async (file, tableName) => {
  const formData = new FormData();
  formData.append('file', file);
  if (tableName) formData.append('table_name', tableName);
  
  const response = await fetch(`${API_BASE_URL}/upload`, {
    method: 'POST',
    body: formData
  });
  
  return response.json();
};