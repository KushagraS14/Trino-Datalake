const { Client } = require('pg');
const bcrypt = require('bcryptjs');

async function addTestUser() {
    const client = new Client({
        user: 'kushagrasrivastava',
        host: 'localhost',
        database: 'tcai_data_lake',
        port: 5432,
    });

    try {
        await client.connect();
        console.log('✅ Connected to database');
        
        // Hash the password
        const hashedPassword = await bcrypt.hash('admin123', 10);
        
        // Insert the test user
        const result = await client.query(
            `INSERT INTO users (email, password_hash, full_name, role, is_active) 
             VALUES ($1, $2, $3, $4, $5)
             ON CONFLICT (email) DO UPDATE 
             SET password_hash = EXCLUDED.password_hash,
                 full_name = EXCLUDED.full_name,
                 role = EXCLUDED.role
             RETURNING id, email, role`,
            ['admin@tcai.com', hashedPassword, 'Admin User', 'admin', true]
        );
        
        console.log('✅ Test user added successfully!');
        console.log('📧 Email: admin@tcai.com');
        console.log('🔑 Password: admin123');
        console.log(`👤 User ID: ${result.rows[0].id}`);
        console.log(`👔 Role: ${result.rows[0].role}`);
        
        await client.end();
    } catch (err) {
        console.error('❌ Error:', err);
    }
}

addTestUser();


