import os
from pypdf import PdfWriter


def merge_pdfs_interactively():
    # 1. Filter for PDF files in the specified directory

    directory = "C:/Users/jdhou/OneDrive/Documents/Knowledge/Products Reference/Databricks Documentation/Merged PDFs"

    files = [f for f in os.listdir(directory) if f.lower().endswith(".pdf")]

    if not files:
        print("No PDF files found in this directory.")
        return

    # 2. Display files to the user
    print("\nAvailable PDFs:")
    for i, filename in enumerate(files, 1):
        print(f"[{i}] {filename}")

    # 3. Get user selection
    selection = input("\nEnter the numbers to merge, separated by commas (e.g., 1, 3, 2): ")

    try:
        # Convert input string to a list of integers (adjusting for 0-indexing)
        indices = [int(n.strip()) - 1 for n in selection.split(",")]

        merger = PdfWriter()

        # 4. Append files in the specific order chosen by user
        for idx in indices:
            file_path = os.path.join(directory, files[idx])
            print(f"Adding: {files[idx]}...")
            merger.append(file_path)

        # 5. Save the output
        output_name = ("Databricks_doco_merged_11.pdf")
        with open(output_name, "wb") as output_file:
            merger.write(output_file)

        merger.close()
        print(f"\nSuccess! Merged file saved as: {output_name}")

    except (ValueError, IndexError):
        print("Invalid selection. Please ensure you enter valid numbers from the list.")


if __name__ == "__main__":
    merge_pdfs_interactively()