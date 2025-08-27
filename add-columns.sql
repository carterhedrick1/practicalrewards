-- Add missing columns to existing cards table
-- Run this in your Supabase SQL Editor

-- Add welcome_bonus column
ALTER TABLE cards ADD COLUMN IF NOT EXISTS welcome_bonus TEXT;

-- Add practical_advice column  
ALTER TABLE cards ADD COLUMN IF NOT EXISTS practical_advice TEXT;

-- Verify the columns were added
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'cards' 
AND column_name IN ('welcome_bonus', 'practical_advice'); 