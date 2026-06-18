const { Client } = require('pg');

console.log('Script started...');

const client = new Client({
    user: 'kushagrasrivastava',
    host: 'localhost',
    database: 'tcai_data_lake',
    port: 5432,
});

console.log('Attempting to connect...');

client.connect()
    .then(() => {
        console.log('✅ Connected successfully!');
        return client.end();
    })
    .then(() => {
        console.log('✅ Connection closed');
    })
    .catch(err => {
        console.error('❌ Error:', err.message);
    });
