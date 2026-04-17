import os
import pandas as pd
from pathlib import Path


# def get_comma_separated_files(directory_path):
"""
Returns a comma-separated string of all file paths within 
the specified directory.
"""
directory_path = "C:/Users/jdhou/OneDrive/Documents/My Kindle Content_KFX-ZIP"

    #("C:/Users/jdhou/OneDrive/Documents/Knowledge/Books/Thompson, John K/Building Analytics Teams/Chapters and Summary/extracted_text_files")
path_obj = Path(directory_path)

# Check if path exists and is a directory to avoid errors
if not path_obj.is_dir():
    print("Error: Path is not a valid directory.")
    #return "Error: Path is not a valid directory."

# Use a list comprehension to gather all items that are files
# .as_posix() ensures forward slashes for cross-platform compatibility
files = [f.absolute().as_posix() for f in path_obj.iterdir() if f.is_file()]
folders = [f.absolute().as_posix() for f in path_obj.iterdir()] # use this for folders

print("; ".join(files))
# print("; ".join(folders))

"""
# Following is to get a row-by-row list of files (or folders) from a directory  instead, e.g. for pasting into Excel

files = [f.absolute().as_posix() for f in path_obj.iterdir() if f.is_file()] 
df = pd.DataFrame(files)
# Prevent long strings (like file paths) from being truncated
pd.set_option('display.max_colwidth', None)
# Ensure the width of the display is large enough to prevent wrapping
pd.set_option('display.width', None)
print(df)

"""


# return ", ".join(files)

# Example usage:
# print(get_comma_separated_files("./my_folder"))