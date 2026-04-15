import os
from pathlib import Path
import comtypes.client

# Constant value 17 is the integer code Word uses for the PDF file format
wdFormatPDF = 17

DOC_FOLDER = r"C:\Users\jdhou\OneDrive\Documents\Learning\Economics\Thesis"
# This is where the output PDFs will be saved (optional, can be the same folder)
PDF_OUTPUT_FOLDER = r"C:\Users\jdhou\OneDrive\Documents\Learning\Economics\Thesis\Thesis_PDF_Format"

def convert_doc_to_pdf(directory_path, output_dir=None):
    """
    Loops through all .doc files in a directory and converts them to PDF
    using Microsoft Word via the comtypes library.

    Args:
        directory_path (str): The path to the directory containing .doc files.
        output_dir (str, optional): The directory to save the PDFs.
                                     Defaults to the input directory.
    """
    input_path = Path(directory_path)
    # Set the output path, defaulting to the input directory if not specified
    output_path = Path(output_dir) if output_dir else input_path

    if not output_path.exists():
        os.makedirs(output_path)
        print(f"Created output directory: {output_path}")

    word = None
    try:
        # 1. Create a Word Application object
        print("Starting Microsoft Word automation...")
        word = comtypes.client.CreateObject('Word.Application')
        # We don't need to see the application window
        word.Visible = False

        print(f"Searching for .doc files in: {input_path}")

        # 2. Iterate over all files ending with '.doc' in the directory
        for doc_file in input_path.glob("*.doc"):
            doc_path = str(doc_file.resolve())
            pdf_name = doc_file.stem + ".pdf"
            pdf_path = str((output_path / pdf_name).resolve())

            print(f"    -> Converting: {doc_file.name}...")

            # Open the document
            doc = word.Documents.Open(doc_path)

            # Save the opened document as a PDF
            doc.SaveAs(pdf_path, FileFormat=wdFormatPDF)

            # Close the document without saving any incidental changes (SaveChanges=0)
            doc.Close(SaveChanges=0)
            print(f"    -> Converted successfully to: {pdf_path}")

    except Exception as e:
        print(f"\nAN ERROR OCCURRED: {e}")
        print("Ensure Microsoft Word is fully functional and not running other modal windows.")
    finally:
        # 3. Always quit the Word application to release resources
        if word:
            word.Quit()
            print("\nMicrosoft Word application closed.")


convert_doc_to_pdf(DOC_FOLDER, PDF_OUTPUT_FOLDER)