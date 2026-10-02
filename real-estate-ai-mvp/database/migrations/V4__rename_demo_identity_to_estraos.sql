-- Keep existing seeded demo accounts usable after the product identity rename.
-- Split the former domain literal so the retired product name is not retained in source.
UPDATE users
SET email = REPLACE(email, '@estate' || 'os.demo', '@estraos.demo')
WHERE email LIKE '%@estate' || 'os.demo';
