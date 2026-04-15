import os
import sys
from pypdf import PdfReader, PdfWriter


def compress_pdf(input_path: str, output_path: str):
    """
    Compresses a PDF file by writing it to a new file with content streams compressed.

    This optimization primarily targets text, line art, and graphics streams within
    the PDF, which can often reduce the file size significantly.

    Args:
        input_path: The path to the original PDF file.
        output_path: The path where the compressed PDF file will be saved.
    """
    try:
        # Check if the input file exists
        if not os.path.exists(input_path):
            print(f"Error: Input file not found at '{input_path}'")
            return

        # Initialize reader and writer objects
        reader = PdfReader(input_path)
        writer = PdfWriter()

        # Iterate over all pages and add them to the writer
        for page in reader.pages:
            writer.add_page(page)

        # IMPORTANT: Enable content stream compression.
        # This is the key step for file size reduction, as it applies filters
        # to compress text and vector graphics data.
        writer.compress_content_streams = True

        # Write the compressed PDF to the specified output path
        with open(output_path, "wb") as output_file:
            writer.write(output_file)

        # Get file sizes for comparison
        original_size = os.path.getsize(input_path)
        compressed_size = os.path.getsize(output_path)

        # Calculate percentage reduction
        if original_size > 0:
            reduction_percent = (1 - (compressed_size / original_size)) * 100
        else:
            reduction_percent = 0

        print("\n--- Compression Results ---")
        print(f"Original File: {input_path}")
        print(f"Compressed File: {output_path}")
        print(f"Original Size: {original_size / (1024 * 1024):.2f} MB")
        print(f"Compressed Size: {compressed_size / (1024 * 1024):.2f} MB")
        print(f"Size Reduction: {reduction_percent:.2f}%")
        print("---------------------------\n")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == '__main__':
    # Simple argument handling for command-line use
    if len(sys.argv) < 3:
        print("Usage: python pdf_compressor.py <input_pdf_path> <output_pdf_path>")
        print("\nExample:")
        print("python pdf_compressor.py document_large.pdf document_small.pdf")
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2]

        # Ensure the output file name is different from the input file name
        if input_file == output_file:
            print("Error: Input and output file paths must be different.")
        else:
            compress_pdf(input_file, output_file)