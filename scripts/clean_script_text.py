import unicodedata  # <-- ADD THIS IMPORT AT THE TOP OF YOUR FILE
import re
import os

from generate_reports_and_scripts_async import load_text, save_text

script_path = "Generate Audio/queued_scripts/24_European History Carolingians and the Frankish Realm 750 to 987 20251113-145522+0800_SCRIPT.txt"
text = load_text(script_path)
filename_only = os.path.basename(script_path)
output_dir = "Generate Audio/queued_scripts"
output_path = os.path.join(output_dir, f"{filename_only}_CLEANED.txt")

# NEW STEP 1: Aggressive Unicode Normalization and Control Character Cleanup

# Normalize the text (e.g., combining characters into standard forms)
corrected_text = unicodedata.normalize('NFC', text)

# Remove zero-width characters (U+200B, U+200C, etc.) which can be invisible markers.
corrected_text = re.sub(r'[\u200b\u200c\u200d\uFEFF]', '', corrected_text)

# Remove C0 and C1 control characters (excluding standard whitespace like \n, \t)
# This removes null bytes, vertical tab, form feed, and other non-printing controls.
# Pattern: [\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]
control_char_pattern = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
corrected_text = control_char_pattern.sub('', corrected_text)

# Rule 1: Find and delete any occurrence of characters *, **, or #.
# (Existing logic from here)
corrected_text = corrected_text.replace('**', '')
corrected_text = corrected_text.replace('*', '')
corrected_text = corrected_text.replace('#', '')

# Correct malformed SSML break tags (prevents user's LLM from breaking the script)
corrected_text = corrected_text.replace('<break="1s"/>', '<break time="1s"/>')
corrected_text = corrected_text.replace('<break="2s"/>', '<break time="2s"/>')

# Rule 3: Replace occurrences of the text 'let's quickly' with 'let's briefly'.
corrected_text = re.sub(
    r"et[’']s quickly",
    "et's briefly",
    corrected_text,
    flags=re.IGNORECASE
)

# Rule 2: Ensure there is a full-stop at the end of each section heading
corrected_text = re.sub(
    r'^([A-Z0-9\s,\'\"\(\)\-\/\&]+)(?<![\.\!\?])\s*$',
    r'\1.',
    corrected_text,
    flags=re.MULTILINE
)

save_text(output_path, corrected_text)
# print(f"Cleaned script {filename_only}")
