import pandas as pd

# Path to your JSON file
file_path = "Luvvoice_Voices_List.json"

# Read JSON file into a DataFrame
df = pd.read_json(file_path)

# Display as a table in console
print(df.to_string(index=False))

# Optional: export to CSV
df.to_csv("Luvvoice_Voices_List.csv", index=False)
