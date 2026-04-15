import os
import re
import base64
import requests
# import pymupdf.layout  # this must precede import pymupdf4llm to activate PyMuPDF’s layout feature. Anyway this didn't run cleanly
import pymupdf4llm
import fitz
from pathlib import Path

# --- CONFIGURATION ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SOURCE_DIR = "C:/Users/jdhou/OneDrive/Documents/Knowledge/Books/Thompson, John K/Building Analytics Teams/Chapters and Summary"
OUTPUT_DIR = ("C:/Users/jdhou/OneDrive/Documents/Knowledge/Books/Thompson, John K/Building Analytics Teams/Chapters and Summary"
              "/extracted_text_files")
IMAGE_TEMP_DIR = "./temp_images"  # Where pymupdf4llm will drop images
MODEL = "google/gemini-2.5-flash-lite"


def get_image_summary(image_path):
    """Reads a saved image file and gets a summary from the LLM."""
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode('utf-8')

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text",
                 "text": "Describe this chart, table-image, or diagram from a document in 1-2 sentences. Review in detail, "
                         "describe the core meaning/conclusion/ data."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
            ]
        }]
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        return response.json()['choices'][0]['message']['content'].strip()
    except:
        return "[Visual element description unavailable]"


def extract_clean_markdown(pdf_path):
    # 1. Open the document to get its page size
    doc = fitz.open(pdf_path)
    model_page = doc[0]
    width, height = model_page.rect.width, model_page.rect.height
    # 2. Define the margins (in points) to strip headers and footers
    # Adjust these numbers if you still see headers/footers
    header_margin = 50
    footer_margin = 50
    # 3. Define the 'clip' rectangle: (x0, y0, x1, y1)
    extraction_box = (0, header_margin, width, height - footer_margin)
    # 2. Set the cropbox (x0, y0, x1, y1)
    for page in doc:
        page.set_cropbox(fitz.Rect(extraction_box))
    # 3. Save as a new document to apply changes for tools
    #for page in doc:
     #   page.set_cropbox(fitz.Rect(50, 50, 550, 750))  # Apply the new crop box to the page
    # doc.save("cropped.pdf")
    # 4. Use pymupdf4llm with the clip parameter
    # write_images=True tells it to extract images and put ![] links in the MD
    md_text = pymupdf4llm.to_markdown(
        doc
        #use_ocr=False, # arg only if using pymupdf-layout, which didn't run
        #header=False, # arg only if using pymupdf-layout, which didn't run
        #footer=False, # arg only if using pymupdf-layout, which didn't run
        ,write_images=True,
        image_path=IMAGE_TEMP_DIR,
        image_format="png"
        # , clip=extraction_box  # <--- This removes headers/footers
    )

    doc.close()
    return md_text


def process_pdfs():
    # Ensure directories exist
    for d in [OUTPUT_DIR, IMAGE_TEMP_DIR]:
        if not os.path.exists(d): os.makedirs(d)

    for filename in os.listdir(SOURCE_DIR):
        if not filename.lower().endswith(".pdf"): continue
        if "book_summary" in filename.lower() or 'book summary' in filename.lower():
            continue

        pdf_path = os.path.join(SOURCE_DIR, filename)
        output_txt_path = os.path.join(OUTPUT_DIR, f"{Path(filename).stem}.md")

        print(f"--- Processing: {filename} ---")

        # 1. Convert PDF to Markdown and save images to a subfolder
        md_content = extract_clean_markdown(pdf_path)

        # 2. Find all image links in the generated Markdown
        # Pattern matches ![](temp_images/image_name.png)
        image_links = re.findall(r"!\[\]\((.*?)\)", md_content)

        # 3. Iterate through links, get summaries, and replace them in the MD
        for rel_path in image_links:
            # Construct absolute path to the image file
            abs_image_path = os.path.join(os.getcwd(), rel_path)
            if os.path.exists(abs_image_path):
                print(f"  > Summarizing visual: {rel_path}...")
                summary = get_image_summary(abs_image_path)
                # Replace the ![](path) with a descriptive block for the LLM
                replacement_text = f"\n\n> [VISUAL CONTENT SUMMARY]: {summary}\n\n"
                md_content = md_content.replace(f"![]({rel_path})", replacement_text)
                # Optional: Clean up the image file after summarizing to save space
                # os.remove(abs_image_path)

        # 4. Save the final LLM-ready Markdown
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Done. Saved Jinja-ready Markdown to {output_txt_path}")


if __name__ == "__main__":
    process_pdfs()