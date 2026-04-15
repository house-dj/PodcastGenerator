import os
import argparse
from pathlib import Path

directory_path = 'Generate Text Scripts\generated_text_files\length checking dir'


"""
Finds all .txt files in the given directory, loops through them,
and outputs their length in characters (Unicode safe).

Args:
directory_path: The path to the directory to scan (default is current directory).
"""

base_dir = Path(directory_path).resolve()
print(f"--- Analyzing text files in: {base_dir} ---")

# Check if the directory exists
if not base_dir.is_dir():
    print(f"Error: Directory not found at {directory_path}")

# 1. Use iterdir() to list contents and filter for .txt files

try:
    text_files = [p for p in base_dir.iterdir() if p.is_file() and p.suffix.lower() == '.txt']
except OSError as e:
    print(f"Error: Could not access directory contents. Check permissions. ({e})")

if not text_files:
    print("No .txt files found in the specified directory.")

# 2. Loop through the found files and calculate length
for file_path in text_files:
    try:
        # Open the file and read its content (using 'utf-8' encoding for character counting)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Calculate the length of the content string
        # char_length = len(content)
        # Calculate the word count by splitting the content string by whitespace
        word_count = len(content.split())

        # Output the filename and its length
        #if word_count < 4750:
        print(f"File: {file_path.name:<25} | Word Count: {word_count}")

    except UnicodeDecodeError:
        # Handles files that might not be standard text
        print(f"File: {file_path.name:<25} | Could not decode (might be binary or wrong encoding).")
    except IOError as e:
        # Handles permission errors or other file system issues
        print(f"File: {file_path.name:<25} | Error reading file: {e}")

