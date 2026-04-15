import os


def rename_files_by_date():
    # 1. Gather all files in the directory with their modification times
    directory = "C:/Users/jdhou/OneDrive/Documents/Knowledge/Products Reference/Databricks"
    files = []
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)

        # Only process files (skip directories)
        if os.path.isfile(filepath):
            mod_time = os.path.getmtime(filepath)
            files.append((filename, mod_time))

    # 2. Sort files by the modification time (oldest to newest)
    files.sort(key=lambda x: x[1])

    # 3. Rename the files
    print(f"Found {len(files)} files. Renaming...")

    # Determine padding based on number of files (e.g., "01" if < 100 files)
    padding = len(str(len(files)))
    if padding < 2: padding = 2

    for index, (filename, _) in enumerate(files, 1):
        # Create the prefix (e.g., "01_")
        prefix = f"{index:0{padding}}_"

        # Avoid double-prefixing if you run the script twice
        if filename.startswith(prefix):
            print(f"Skipping: {filename} (already prefixed)")
            continue

        old_path = os.path.join(directory, filename)
        new_path = os.path.join(directory, f"{prefix}{filename}")

        os.rename(old_path, new_path)
        print(f"Renamed: {filename} -> {prefix}{filename}")

    print("\nDone!")


if __name__ == "__main__":
    # You can pass a specific path here, e.g., rename_files_by_date("C:/MyPDFs")
    rename_files_by_date()