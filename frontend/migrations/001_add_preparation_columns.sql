-- Adds the new preparation-related columns to the MySQL `medicinal_plants`
-- table used by frontend/app.py's Explore Herb / Dashboard pages.
--
-- Run this against your local `nativemed_ai` MySQL database once, e.g.:
--     mysql -u root -p nativemed_ai < migrations/001_add_preparation_columns.sql
--
-- After running this, re-run `python import_dataset.py` from the frontend/
-- folder to (re)populate these columns from the updated
-- dataset/Cleaned_Medicinal_Plants_Dataset.xlsx. import_dataset.py now
-- upserts by plant_id, so it's safe to run again on top of existing data.

-- Each column is its own ALTER TABLE statement (rather than one combined
-- statement) so that running this with `mysql --force` will skip over any
-- column that already exists (e.g. from a previous partial run) instead of
-- aborting the whole migration.
ALTER TABLE medicinal_plants ADD COLUMN preparation_method TEXT;
ALTER TABLE medicinal_plants ADD COLUMN how_to_take TEXT;
ALTER TABLE medicinal_plants ADD COLUMN general_disclaimer TEXT;
