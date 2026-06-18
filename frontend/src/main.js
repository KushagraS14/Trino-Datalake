import './style.css'
const token =
  localStorage.getItem("token");

if (token) {
  document.getElementById(
    "loginScreen"
  ).style.display = "none";

  document.getElementById(
    "appContainer"
  ).style.display = "block";
}
const loginBtn = document.getElementById("loginBtn");

if (loginBtn) {
  loginBtn.addEventListener("click", async () => {
    const email =
      document.getElementById("email").value;

    const password =
      document.getElementById("password").value;

    try {
      const response = await fetch(
        "http://127.0.0.1:5001/login",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            email,
            password
          })
        }
      );

      const result = await response.json();

      if (response.ok) {
        localStorage.setItem(
          "token",
          result.token
        );

        localStorage.setItem(
          "role",
          result.role
        );

        document.getElementById(
          "loginScreen"
        ).style.display = "none";

        document.getElementById(
          "appContainer"
        ).style.display = "block";
      } else {
        document.getElementById(
          "loginError"
        ).innerText =
          result.error;
      }
    } catch (err) {
      console.error(err);
    }
  });
}
let currentChart = null; 
let globalColumns = []; 
let globalRows = [];

// DOM Elements
const runBtn = document.getElementById('runQueryBtn');
const sqlInput = document.getElementById('sqlInput');
const chartControls = document.getElementById('chartControls');
const chartColumnSelect = document.getElementById('chartColumn');
const chartTypeSelect = document.getElementById('chartType');
const tableContainer = document.getElementById('tableContainer');
// Add this function near the top of main.js (after DOM elements)
function isDangerousQuery(query) {
  const upperQuery = query.toUpperCase().trim();
  return upperQuery.startsWith('INSERT') || 
         upperQuery.startsWith('UPDATE') || 
         upperQuery.startsWith('DELETE') ||
         upperQuery.startsWith('DROP') ||
         upperQuery.startsWith('TRUNCATE');
}

// Then update the runBtn click handler to include confirmation:
runBtn.addEventListener('click', async () => {
  const customQuery = sqlInput.value.trim();
  if (!customQuery) {
    alert("Please enter a SQL query!");
    return;
  }

  // Add confirmation for dangerous queries
  if (isDangerousQuery(customQuery)) {
    const confirmed = confirm(`⚠️ You are about to run a ${customQuery.split(' ')[0]} query.\n\nThis will modify your data.\n\nAre you sure you want to continue?`);
    if (!confirmed) {
      return;
    }
  }

  
});
// --- SQL EDITOR GUTTER SYNC ---
const gutter = document.querySelector('.sql-editor-gutter');
if (gutter && sqlInput) {
    const syncLineNumbers = () => {
        const lines = sqlInput.value.split('\n').length;
        gutter.innerHTML = Array.from({ length: lines }, (_, i) => `<span>${i + 1}</span>`).join('');
    };
    sqlInput.addEventListener('input', syncLineNumbers);
    sqlInput.addEventListener('scroll', () => {
        gutter.scrollTop = sqlInput.scrollTop;
    });
    syncLineNumbers();
}

// --- 1. UPLOAD & INGESTION LOGIC ---
const uploadBtn = document.getElementById('uploadBtn');
const fileInput = document.getElementById('fileInput');

if (uploadBtn && fileInput) {
  // In your main.js, find the upload click handler and update it:
// In your main.js, find the upload click handler and update it:
uploadBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];

    if (!file) {
        alert("Please select a file (CSV, XLSX, JSON, Parquet)!");
        return;
    }

    const allowedExtensions = ["csv", "xlsx", "json", "parquet"];
    const ext = file.name.split(".").pop().toLowerCase();

    if (!allowedExtensions.includes(ext)) {
        alert("Only CSV, XLSX, JSON, Parquet files are allowed!");
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    
    try {
        // CHANGE THIS - Use /ingest with API key
        const response = await fetch('http://127.0.0.1:5001/ingest', {
            method: 'POST',
            body: formData,
            headers: {
                'X-API-KEY': 'trino-secure-key-2026'  // Add this header
            }
        });

        const result = await response.json();

        if (response.ok) {
            // Note: /ingest returns 'table' not 'table_name'
            alert("Success: " + result.message);
            
            if (result.table) {  // Changed from result.table_name to result.table
                sqlInput.value = `SELECT * FROM datalake.analytic.${result.table} LIMIT 10;`;
                if (gutter) {
                    const lines = sqlInput.value.split('\n').length;
                    gutter.innerHTML = Array.from({ length: lines }, (_, i) => `<span>${i + 1}</span>`).join('');
                }
                // Auto-run the query
                runBtn.click();
            }
        } else {
            alert("Upload Error: " + result.error);
        }
    } catch (error) {
        console.error("Upload failed", error);
        alert("Failed to connect to the backend ingestion route.");
    }
});
// --- 2. SCHEMA DICTIONARY RENDERER ---
function displaySchemaMapping(mapping) {
    const dictionaryDiv = document.getElementById('schemaDictionary');
    const tbody = document.getElementById('mappingTableBody');
    
    tbody.innerHTML = ''; 

    for (const [originalName, sqlName] of Object.entries(mapping)) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${originalName}</td>
            <td>${sqlName}</td>
        `;
        tbody.appendChild(tr);
    }
    
    dictionaryDiv.style.display = 'block';
}


/// --- 3. QUERY EXECUTION LOGIC (UPDATED for INSERT support) ---
runBtn.addEventListener('click', async () => {
  const customQuery = sqlInput.value.trim();
  if (!customQuery) {
    alert("Please enter a SQL query!");
    return;
  }

  tableContainer.innerHTML = `
    <div class="empty-state">
      <div class="loading" style="margin-bottom: 12px;"></div>
      <div class="empty-state-text">Executing query in Trino...</div>
    </div>
  `;
  chartControls.style.display = 'none';

  try {
    const response = await fetch('http://127.0.0.1:5001/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: customQuery })
    });

    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Query Failed. Check your SQL syntax.');

    // NEW: Check if this is an INSERT response
    if (result.success !== undefined) {
      // This is an INSERT/DML operation
      const message = result.message || 'Query executed successfully';
      const rowsAffected = result.rows_affected || 0;
      
      tableContainer.innerHTML = `
        <div class="empty-state" style="color: var(--green);">
          <div class="empty-state-icon"><i class="fas fa-check-circle"></i></div>
          <div class="empty-state-text" style="font-size: 18px; margin-bottom: 8px;">✓ Success!</div>
          <div class="empty-state-text">${message}</div>
          <div class="empty-state-text" style="font-size: 14px; margin-top: 8px;">Rows affected: ${rowsAffected}</div>
        </div>
      `;
      
      // Clear any existing chart
      if (currentChart) {
        currentChart.destroy();
        currentChart = null;
      }
      chartControls.style.display = 'none';
      return;
    }

    // This is a SELECT response (original logic)
    globalColumns = result.columns;
    globalRows = result.rows;
    
    renderTable(globalColumns, globalRows, tableContainer);
    setupChartControls(globalColumns);

  } catch (error) {
    tableContainer.innerHTML = `<p style="color: var(--red); font-weight: bold; padding: 20px;">Error: ${error.message}</p>`;
    if (currentChart) currentChart.destroy();
  }
});

// --- 4. SETUP CHART DROPDOWNS ---
function setupChartControls(columns) {
  if (!columns || columns.length === 0) return;

  chartColumnSelect.innerHTML = '';
  columns.forEach((col, index) => {
    const option = document.createElement('option');
    option.value = index;
    option.text = col;
    chartColumnSelect.appendChild(option);
  });

  if (columns.length > 1) {
    chartColumnSelect.value = 1;
  }

  chartControls.style.display = 'flex';
  renderChart();
}

chartColumnSelect.addEventListener('change', renderChart);
chartTypeSelect.addEventListener('change', renderChart);


// --- 5. RENDER CHART LOGIC ---
function renderChart() {
  if (!globalRows || globalRows.length === 0) return;

  const targetColIndex = parseInt(chartColumnSelect.value); 
  const chartType = chartTypeSelect.value;
  const colName = globalColumns[targetColIndex];
  
  const counts = {};

  globalRows.forEach(row => {
    const value = row[targetColIndex] !== null ? row[targetColIndex] : 'NULL';
    counts[value] = (counts[value] || 0) + 1;
  });

  const chartLabels = Object.keys(counts);
  const chartData = Object.values(counts);

  if (currentChart) currentChart.destroy();

  const ctx = document.getElementById('myChart').getContext('2d');
  currentChart = new Chart(ctx, {
    type: chartType, 
    data: {
      labels: chartLabels,
      datasets: [{
        label: 'Row Count',
        data: chartData,
        backgroundColor: ['#c9a84c', '#1a7a6e', '#5b9cf6', '#c084fc', '#ef4444', '#06b6d4', '#ec4899', '#f97316'],
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      plugins: {
        title: {
          display: true,
          text: `Record Count Grouped By: ${colName}`,
          font: { size: 14, family: "'DM Sans', sans-serif" }
        },
        legend: {
          labels: { font: { family: "'DM Sans', sans-serif" } }
        }
      }
    }
  });
}
document
  .getElementById("logoutBtn")
  .addEventListener("click", () => {

    localStorage.removeItem("token");
    localStorage.removeItem("role");

    location.reload();
});
document.getElementById("logoutBtn").addEventListener("click", function() {
    window.location.href = "index.html";
});
// --- 6. RENDER TABLE LOGIC ---
function renderTable(columns, rows, container) {
  if (!rows || rows.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon"><i class="fas fa-inbox"></i></div><div class="empty-state-text">No data returned.</div></div>';
    return;
  }

  let html = '<table>';
  html += '<thead><tr>';
  columns.forEach(col => { html += `<th>${col}</th>`; });
  html += '</tr></thead><tbody>';
  
  rows.forEach(row => {
    html += '<tr>';
    row.forEach(cell => { html += `<td>${cell !== null ? cell : '<span style="color: var(--ink-soft); font-style: italic;">NULL</span>'}</td>`; });
    html += '</tr>';
  });
  
  html += '</tbody></table>';
  container.innerHTML = html;
}


// --- 7. SUGGESTION BUTTON LOGIC ---
const suggestButtons = document.querySelectorAll('.suggest-btn');

suggestButtons.forEach(btn => {
  btn.addEventListener('click', (event) => {
    event.preventDefault();
    const queryToRun = btn.getAttribute('data-query');
    sqlInput.value = queryToRun;
    runBtn.click(); 
  });
});}