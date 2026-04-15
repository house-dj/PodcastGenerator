import os
from pathlib import Path


# def get_comma_separated_files(directory_path):
"""
Returns a comma-separated string of all file paths within 
the specified directory.
"""
directory_path = ("C:/Users/jdhou/OneDrive/Documents/Knowledge/Books/Thompson, John K/Building Analytics Teams/Chapters and Summary"
              "/extracted_text_files")
path_obj = Path(directory_path)

# Check if path exists and is a directory to avoid errors
if not path_obj.is_dir():
    print("Error: Path is not a valid directory.")
    #return "Error: Path is not a valid directory."

# Use a list comprehension to gather all items that are files
# .as_posix() ensures forward slashes for cross-platform compatibility
files = [f.absolute().as_posix() for f in path_obj.iterdir() if f.is_file()]

print("; ".join(files))

# return ", ".join(files)

# Example usage:
# print(get_comma_separated_files("./my_folder"))