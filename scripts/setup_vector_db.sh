#!/bin/bash
# Setup vector_db database with proper permissions

echo "Setting up vector_db database..."

# Set password for postgres user
sudo -u postgres psql << EOF
ALTER USER postgres WITH PASSWORD 'postgres';
\q
EOF

echo "✅ Password set for postgres user"

# Create vector_db if it doesn't exist
sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw vector_db
if [ $? -ne 0 ]; then
    sudo -u postgres psql -c "CREATE DATABASE vector_db;"
    echo "✅ Created vector_db database"
else
    echo "✅ vector_db database already exists"
fi

# Enable pgvector extension
sudo -u postgres psql -d vector_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
echo "✅ Enabled pgvector extension"

# Grant permissions
sudo -u postgres psql -d vector_db << EOF
GRANT ALL PRIVILEGES ON DATABASE vector_db TO postgres;
GRANT ALL ON SCHEMA public TO postgres;
\q
EOF

echo "✅ Granted permissions"

# Test connection
echo ""
echo "Testing connection..."
PGPASSWORD=postgres psql -h localhost -U postgres -d vector_db -c "SELECT version();" > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Connection test successful!"
    echo ""
    echo "Database URL: postgresql://postgres:postgres@localhost:5432/vector_db"
else
    echo "❌ Connection test failed"
    exit 1
fi

echo ""
echo "✅ Database setup complete!"
