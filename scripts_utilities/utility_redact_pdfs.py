import fitz  # PyMuPDF
import os


def redact_pdf_text(directory_path, search_term):
    output_dir = os.path.join(directory_path, "redacted_pdfs")
    os.makedirs(output_dir, exist_ok=True)

    for filename in os.listdir(directory_path):
        if filename.lower().endswith(".pdf"):
            path = os.path.join(directory_path, filename)
            doc = fitz.open(path)

            for page in doc:
                # 1. Find the text coordinates
                areas = page.search_for(search_term)

                # 2. Apply redaction annotations to those areas
                for area in areas:
                    page.add_redact_annot(area, fill=(0, 0, 0))  # Black box

                # 3. Permanently "burn" the redaction into the PDF
                page.apply_redactions()

            output_path = os.path.join(output_dir, f"redacted_{filename}")
            doc.save(output_path, garbage=4, deflate=True)
            doc.close()
            print(f"Redacted and saved: {filename}")


# Usage: This will black out every mention of "King Rat"
redact_pdf_text('C:/Users/jdhou/OneDrive/Documents/Personal/Roleplaying/Modules/Scribd upload/Queue', 'King Rat')