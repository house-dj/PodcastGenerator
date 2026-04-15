import pathlib
import os
import re # New import for regular expressions

directory='generated_text_files/cleanup'

# --- Constants for Ordinal Conversion ---
# Mappings for Roman Numerals to Ordinals (up to XII)
ROMAN_ORDINAL_MAP = {
    'I': 'the First',
    'II': 'the Second',
    'III': 'the Third',
    'IV': 'the Fourth',
    'V': 'the Fifth',
    'VI': 'the Sixth',
    'VII': 'the Seventh',
    'VIII': 'the Eighth',
    'IX': 'the Ninth',
    'X': 'the Tenth',
    'XI': 'the Eleventh',
    'XII': 'the Twelfth',
}

"""
    Loops through all .txt files in the specified directory, reads their content,
    performs two types of cleaning:
    1. Replaces case-sensitive Roman numerals (I-XII) following any capitalized name
       (e.g., Charles I -> Charles, the First).
    2. Removes occurrences of '*', '**', and '#'.

    The file is overwritten with the cleaned content if changes were made.

    Args:
        directory (str): The path to the directory to scan. Defaults to the
                         current directory ('.').
    """

# Characters to be removed (unstructured markdown)
chars_to_remove = ['**', '*', '#']

target_dir = pathlib.Path(directory)

if not target_dir.is_dir():
    print(f"Error: Directory not found at '{directory}'")

print(f"Scanning directory: {target_dir.resolve()}")
processed_count = 0

# Sort Roman numerals from longest to shortest ('XII' to 'I')
# to prevent partial matches (e.g., 'I' being matched inside 'II').
sorted_romans = sorted(ROMAN_ORDINAL_MAP.keys(), key=len, reverse=True)

# Iterate over all .txt files in the current directory
for file_path in target_dir.glob('*.txt'):
    print(f"Processing file: {file_path.name}")

    try:
        # 1. Read the entire file content
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()

        cleaned_content = original_content

        # --- Phase 1: Roman Numeral to Ordinal Replacement (Name-Independent) ---

        for roman in sorted_romans:
            ordinal = ROMAN_ORDINAL_MAP[roman]

            # Regex pattern:
            # (\b[A-Z]\w*)  -> Capture Group 1: Matches any word starting with an uppercase letter (The Name).
            # \s+           -> Matches one or more spaces.
            # {roman}\b     -> Matches the specific Roman numeral followed by a word boundary.
            # The entire pattern is case-sensitive, fulfilling the requirement.
            pattern = rf"(\b[A-Z]\w*)\s+{roman}\b"

            # Replacement string: Uses the captured name (\1) and adds the ordinal.
            replacement = rf"\1 {ordinal}"

            # Use re.sub to perform the case-sensitive replacement globally
            cleaned_content = re.sub(pattern, replacement, cleaned_content)

        # --- Phase 2: Unstructured Character Removal ---
        for char_to_remove in chars_to_remove:
            cleaned_content = cleaned_content.replace(char_to_remove, '')

        # Check if any changes were actually made
        if original_content != cleaned_content:
            # 3. Write the modified content back to the same file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)
            print(f"  -> Successfully cleaned and updated {file_path.name}")
            processed_count += 1
        else:
            print(f"  -> No changes needed for {file_path.name}")

    except Exception as e:
        print(f"  -> Error processing {file_path.name}: {e}")

print("-" * 30)
print(f"Finished. Total .txt files processed and cleaned: {processed_count}")
print(f"Note: Files that had no changes were not overwritten.")

