import os
import pikepdf

""""
Strips metadata from all pdf files within a directory, moves to a new sub directory
"""

def robust_strip_metadata(directory_path):
    output_dir = os.path.join(directory_path, "cleaned_pdfs")
    os.makedirs(output_dir, exist_ok=True)

    for filename in os.listdir(directory_path):
        if filename.lower().endswith(".pdf"):
            path = os.path.join(directory_path, filename)
            try:
                with pikepdf.open(path) as pdf:
                    # Safely attempt to remove XMP metadata
                    if "/Metadata" in pdf.Root:
                        del pdf.Root.Metadata

                    # Safely clear the Document Information Dictionary
                    # We iterate through keys to ensure it's truly empty
                    try:
                        for key in list(pdf.docinfo.keys()):
                            del pdf.docinfo[key]
                    except AttributeError:
                        pass  # No docinfo present

                    pdf.save(os.path.join(output_dir, filename))
                    print(f"Cleaned: {filename}")
            except Exception as e:
                print(f"Skipped {filename}: {e}")


# Usage
robust_strip_metadata('C:/Users/jdhou/OneDrive/Documents/Personal/Roleplaying/Modules/Scribd upload/Queue')