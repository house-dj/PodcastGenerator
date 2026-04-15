import os
import re
import sys
from datetime import datetime


# ===================== Logging / Utilities =====================

def log(msg: str):
    """Prints a standard log message to stderr."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)


# ===================== Correction Logic =====================

def correct_script_text(text: str) -> str:
    """
    Applies final cleaning steps to the generated script text:
    1. Removes specified markdown characters (*, **, #).
    2. Ensures full-stops on full-caps section headings.
    3. Replaces a common LLM phrase ('let's quickly') with a preferred alternative ('let's briefly').
    """
    if not text:
        return ""

    corrected_text = text

    # Rule 1: Find and delete any occurrence of characters *, **, or #.
    # We remove '**' first to avoid leaving orphaned '*' characters.
    corrected_text = corrected_text.replace('**', '')
    corrected_text = corrected_text.replace('*', '')
    corrected_text = corrected_text.replace('#', '')

    # Rule 3: Replace occurrences of the text 'let's quickly' with 'let's briefly'.
    # Note: Using case-insensitive replacement (re.IGNORECASE) for robustness.
    corrected_text = re.sub(
        r"et[’']s quickly",
        "et's briefly",
        corrected_text,
        flags=re.IGNORECASE
    )

    # Rule 2: Ensure there is a full-stop at the end of each section heading (the full-caps headings).
    # Regex to find a line that:
    # 1. Starts at the beginning of a line (^)
    # 2. Contains 1 or more ALL CAPS characters, digits, spaces, common heading punctuation.
    # 3. Does NOT end with a period, exclamation mark, or question mark (negative lookbehind).
    # 4. Ends right before the line break ($)
    # The replacement adds a dot to the captured group (\1).
    corrected_text = re.sub(
        r'^([A-Z0-9\s,\'\"\(\)\-\/\&]+)(?<![\.\!\?])\s*$',
        r'\1.',
        corrected_text,
        flags=re.MULTILINE
    )

    return corrected_text


# ===================== Main Execution Block =====================

# --- Set your file paths here for direct IDE execution ---
# NOTE: The input file must exist for the script to run without errors.
INPUT_FILE_PATH = "generated_text_files/105_British_History_Late_Anglo-Saxon_Danish_Kings_900_to_1066_20251104-162650+0800_SCRIPT.txt"
OUTPUT_FILE_PATH = "clean_script_output.txt"
# --------------------------------------------------------

if __name__ == "__main__":
    input_path = INPUT_FILE_PATH
    output_path = OUTPUT_FILE_PATH

    log(f"Starting script cleanup for input: {input_path}")

    # 1. Read the input file
    log(f"Reading input file: {input_path}")
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_path}. Please create it or update INPUT_FILE_PATH.",
              file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading input file: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Apply the correction
    log("Applying text corrections...")
    corrected_text = correct_script_text(raw_text)

    # 3. Write the output file
    log(f"Writing corrected text to: {output_path}")
    try:
        # Ensure the directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(corrected_text)

        log(f"Success! Corrected script saved to {output_path}")
    except Exception as e:
        print(f"Error writing output file: {e}", file=sys.stderr)
        sys.exit(1)
