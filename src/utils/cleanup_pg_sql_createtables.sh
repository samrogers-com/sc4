# Remove SEQUENCE commands
sed -i '' '/SEQUENCE NAME/d' postgres_dumptables.sql
sed -i '' '/START WITH/d' postgres_dumptables.sql
sed -i '' '/INCREMENT BY/d' postgres_dumptables.sql
sed -i '' '/NO MINVALUE/d' postgres_dumptables.sql
sed -i '' '/NO MAXVALUE/d' postgres_dumptables.sql
sed -i '' '/CACHE/d' postgres_dumptables.sql

# Convert COPY to INSERT INTO
sed -i '' 's/COPY /INSERT INTO /g' postgres_dumptables.sql
sed -i '' 's/ FROM stdin;/ VALUES/g' postgres_dumptables.sql
sed -i '' 's/\t/, /g' postgres_dumptables.sql
sed -i '' '/^\\\./d' postgres_dumptables.sql

# Remove incorrect INSERT statements with missing values
sed -i '' '/INSERT INTO .* VALUES *;/d' postgres_dumptables.sql

# Ensure session values are quoted
sed -i '' "s/INSERT INTO django_session (session_key, session_data, expire_date) VALUES/\nINSERT INTO django_session (session_key, session_data, expire_date) VALUES/g" postgres_dumptables.sql
# sed -E -i '' 's/^([^)]*)/("\1")/g' postgres_dumptables.sql
sed -E -i '' 's/^(\([^)]*\))/\1/g' postgres_dumptables.sql

# 1️⃣ Add an opening parenthesis after VALUES
sed -E -i '' 's/(INSERT INTO [^ ]+ \([^)]+\) VALUES)/\1\n(/g' postgres_dumptables.sql
# 2️⃣ Wrap each row inside parentheses
sed -E -i '' 's/^([0-9]+,)/(\1/g' postgres_dumptables.sql
# 3️⃣ Ensure the last row ends with a semicolon instead of a comma
sed -E -i '' 's/,$/);/g' postgres_dumptables.sql