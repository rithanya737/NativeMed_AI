import pandas as pd
import mysql.connector

# Connect to MySQL
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="rith737",
    database="nativemed_ai"
)

cursor = conn.cursor()

# Read Excel file
df = pd.read_excel("dataset/Cleaned_Medicinal_Plants_Dataset.xlsx")

# Replace NaN values with empty strings
df = df.fillna("")

# Insert data
for _, row in df.iterrows():

    # Upsert (rather than plain INSERT) so this script can be safely re-run
    # after the dataset is updated (e.g. to add the preparation columns)
    # without hitting a duplicate-primary-key error on already-imported rows.
    sql = """
    INSERT INTO medicinal_plants
    (
        plant_id,
        plant_name,
        botanical_name,
        medicinal_properties,
        traditional_uses,
        cultural_significance,
        diseases_treated,
        preparation_method,
        how_to_take,
        general_disclaimer
    )
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
        plant_name = VALUES(plant_name),
        botanical_name = VALUES(botanical_name),
        medicinal_properties = VALUES(medicinal_properties),
        traditional_uses = VALUES(traditional_uses),
        cultural_significance = VALUES(cultural_significance),
        diseases_treated = VALUES(diseases_treated),
        preparation_method = VALUES(preparation_method),
        how_to_take = VALUES(how_to_take),
        general_disclaimer = VALUES(general_disclaimer)
    """

    values = (
        int(row["Plant Id"]),
        row["Plant Name"],
        row["Botanical Name"],
        row["Medicinal Properties"],
        row["Traditional Uses"],
        row["Cultural Significance"],
        row["Diseases Treated"],
        row["Preparation Method"],
        row["How To Take / Apply"],
        row["General Disclaimer"],
    )

    cursor.execute(sql, values)

conn.commit()

print("Dataset Imported Successfully!")

cursor.close()
conn.close()