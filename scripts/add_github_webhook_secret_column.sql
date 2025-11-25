-- Migration: Add github_webhook_secret column to users table
-- Date: 2025-11-25
-- Description: Add support for per-user GitHub webhook secrets instead of using environment variables

-- Add the column
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS github_webhook_secret TEXT;

-- Add comment for documentation
COMMENT ON COLUMN users.github_webhook_secret IS 'Cryptographically secure webhook secret for GitHub webhook signature verification. Generated uniquely per user.';

-- Create index for faster lookups (optional, but recommended if we query by secret)
-- CREATE INDEX IF NOT EXISTS idx_users_webhook_secret ON users(github_webhook_secret) WHERE github_webhook_secret IS NOT NULL;

-- Verify the column was added
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name = 'github_webhook_secret';
