const { Client } = require('pg');

console.log('🚀 Starting database initialization...');

const client = new Client({
    user: 'kushagrasrivastava',
    host: 'localhost',
    database: 'tcai_data_lake',
    port: 5432,
});

async function initDatabase() {
    console.log('📡 Attempting to connect to PostgreSQL...');
    
    try {
        await client.connect();
        console.log('✅ Connected to database');
        
        // Create users table
        console.log('📋 Creating users table...');
        await client.query(`
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(255),
                role VARCHAR(50) DEFAULT 'user',
                is_active BOOLEAN DEFAULT true,
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        `);
        console.log('✅ Users table created/verified');
        
        // Create sessions table
        console.log('📋 Creating sessions table...');
        await client.query(`
            CREATE TABLE IF NOT EXISTS sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                session_token VARCHAR(255) UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        `);
        console.log('✅ Sessions table created/verified');
        
        console.log('✅ Database initialization complete!');
        await client.end();
        console.log('🔌 Database connection closed.');
        
    } catch (err) {
        console.error('❌ Error:', err);
        console.error('Error details:', err.stack);
        await client.end().catch(() => {});
    }
}

// Execute and handle errors properly
initDatabase().catch(err => {
    console.error('❌ Unhandled error:', err);
    process.exit(1);
});