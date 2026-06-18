const express = require('express');
const bcrypt = require('bcryptjs');
const { Pool } = require('pg');
const cors = require('cors');
const crypto = require('crypto');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());

// Serve static files from the frontend directory
app.use(express.static(path.join(__dirname, 'frontend')));

// PostgreSQL connection
const pool = new Pool({
    user: 'kushagrasrivastava',
    password: '',
    host: 'localhost',
    port: 5432,
    database: 'tcai_data_lake',
});

// Test database connection
pool.connect((err, client, release) => {
    if (err) {
        console.error('❌ Database connection error:', err.stack);
    } else {
        console.log('✅ Connected to PostgreSQL');
        release();
    }
});

// Login endpoint
app.post('/api/login', async (req, res) => {
    const { email, password, rememberMe } = req.body;
    
    try {
        const userResult = await pool.query(
            'SELECT id, email, password_hash, role, is_active FROM users WHERE email = $1',
            [email]
        );
        
        if (userResult.rows.length === 0) {
            return res.status(401).json({ error: 'Invalid email or password' });
        }
        
        const user = userResult.rows[0];
        
        if (!user.is_active) {
            return res.status(401).json({ error: 'Account deactivated' });
        }
        
        const isValid = await bcrypt.compare(password, user.password_hash);
        
        if (!isValid) {
            return res.status(401).json({ error: 'Invalid email or password' });
        }
        
        await pool.query('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = $1', [user.id]);
        
        const sessionToken = crypto.randomBytes(64).toString('hex');
        const expiresAt = new Date();
        
        if (rememberMe) {
            expiresAt.setDate(expiresAt.getDate() + 30);
        } else {
            expiresAt.setHours(expiresAt.getHours() + 24);
        }
        
        await pool.query(
            'INSERT INTO sessions (user_id, session_token, expires_at) VALUES ($1, $2, $3)',
            [user.id, sessionToken, expiresAt]
        );
        
        res.json({
            success: true,
            sessionToken,
            user: {
                id: user.id,
                email: user.email,
                role: user.role
            },
            expiresAt: expiresAt.toISOString()
        });
        
    } catch (error) {
        console.error('Login error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Get current user endpoint
app.get('/api/current-user', async (req, res) => {
    const sessionToken = req.headers.authorization?.split(' ')[1];
    
    if (!sessionToken) {
        return res.status(401).json({ error: 'No session token' });
    }
    
    try {
        const result = await pool.query(
            'SELECT user_id, expires_at FROM sessions WHERE session_token = $1',
            [sessionToken]
        );
        
        if (result.rows.length === 0) {
            return res.status(401).json({ error: 'Invalid session' });
        }
        
        const session = result.rows[0];
        
        if (new Date() > session.expires_at) {
            await pool.query('DELETE FROM sessions WHERE session_token = $1', [sessionToken]);
            return res.status(401).json({ error: 'Session expired' });
        }
        
        const userResult = await pool.query(
            'SELECT id, email, full_name, role FROM users WHERE id = $1',
            [session.user_id]
        );
        
        res.json({ user: userResult.rows[0] });
    } catch (error) {
        console.error('Error:', error);
        res.status(500).json({ error: 'Server error' });
    }
});

// Logout endpoint
app.post('/api/logout', async (req, res) => {
    const sessionToken = req.headers.authorization?.split(' ')[1];
    
    if (sessionToken) {
        await pool.query('DELETE FROM sessions WHERE session_token = $1', [sessionToken]);
    }
    
    res.json({ success: true });
});

// Serve index.html from frontend folder for root route
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'frontend', 'index.html'));
});

// Start server
app.listen(PORT, () => {
    console.log(`🚀 Server running on http://localhost:${PORT}`);
    console.log(`📧 Login with: admin@tcai.com`);
    console.log(`🔑 Password: admin123`);
    console.log(`📁 Serving files from: ${path.join(__dirname, 'frontend')}`);
});
