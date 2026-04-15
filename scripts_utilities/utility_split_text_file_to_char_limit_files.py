import re

# --- Configuration ---
# Maximum character limit for each chunk file
max_chars = 3000

# Name of the input text file
INPUT_FILENAME = "generated_text_files/105_British_History_Late_Anglo-Saxon_Danish_Kings_900_to_1066_20251104-162650+0800_SCRIPT.txt"

# Base name for the output chunk files (e.g., "chunk_0.txt", "chunk_1.txt", etc.)
OUTPUT_BASENAME = "105_British_History_Late_Anglo-Saxon_Danish_Kings_900_to_1066_chunk"

"""
Splits a large block of text into chunks, ensuring:
1. No chunk exceeds the max_chars limit.
2. Splits primarily occur only at sentence-ending punctuation (., ?, !).

Args:
    text: The complete string of text to be split.
    max_chars: The maximum character limit for each chunk.

Returns:
    A list of strings, where each string is a text chunk.
"""

print(f"Attempting to read file: **{INPUT_FILENAME}**")
try:
    # 1. Read the input file
    with open(INPUT_FILENAME, 'r', encoding='utf-8') as f:
        text = f.read()
    print(f"File read successfully. Total characters: **{len(text)}**")

    # 2. Split the text into chunks
    print(f"Splitting text into chunks (max chars: **{max_chars}**)...")

    # Regex to split on sentence delimiters, keeping the delimiter
    # The pattern r'([.?!])\s+' captures the delimiter (., ?, !) in a group
    # and includes any trailing whitespace in the split.
    sentence_delimiters = r'([.?!])\s+'

    # Split the text, then filter out empty strings
    split_pieces = [piece.strip() for piece in re.split(sentence_delimiters, text) if piece.strip()]

    # Recombine sentences and their delimiters into a full sentence structure for easier processing.
    # The split_pieces list contains (sentence_text, delimiter, sentence_text, delimiter, ...)
    sentences = []
    for i in range(0, len(split_pieces), 2):
        sentence_text = split_pieces[i]
        # Check if there's a delimiter after the text piece
        delimiter = split_pieces[i + 1] if i + 1 < len(split_pieces) else ""
        # Reconstruct the full sentence with its delimiter and a single space for separation
        full_sentence = f"{sentence_text}{delimiter} " if delimiter else sentence_text
        sentences.append(full_sentence)

    chunks = []
    current_chunk = ""

    for full_sentence in sentences:

        # 1. Check if adding the new sentence would exceed the limit
        if len(current_chunk) + len(full_sentence) > max_chars and current_chunk:
            # Current chunk is full, so finalize it and start a new one
            chunks.append(current_chunk.strip())
            current_chunk = ""

        # 2. Handle a sentence that is longer than the max_chars limit (must be split mid-sentence)
        if len(full_sentence) > max_chars:
            print(f"⚠️ Warning: Sentence too long ({len(full_sentence)} chars). Splitting mid-sentence.")
            # Finalize the current_chunk before adding the broken-up sentence parts
            if current_chunk:
                chunks.append(current_chunk.strip())

            # Split the excessively long sentence into max_chars segments
            for j in range(0, len(full_sentence), max_chars):
                chunks.append(full_sentence[j:j + max_chars].strip())
            current_chunk = ""  # Ensure the main loop continues with an empty chunk

        # 3. Add the sentence to the current chunk
        else:
            current_chunk += full_sentence

    # Add the final remaining chunk after the loop finishes
    if current_chunk:
        chunks.append(current_chunk.strip())

    print(f"Text split into **{len(chunks)}** chunks.")

    # 3. Write each chunk to a new file
    for i, chunk in enumerate(chunks):
        output_filename = f"{OUTPUT_BASENAME}_{i}.txt"
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(chunk)
        print(f"  - Wrote chunk **{i}** to **{output_filename}** ({len(chunk)} chars)")

    print("\n✅ Script completed successfully.")

except FileNotFoundError:
    print(f"\n❌ Error: Input file **'{INPUT_FILENAME}'** not found.")
    print("Please ensure you have created a text file named 'input_text_file.txt' in the same directory.")
except Exception as e:
    print(f"\n❌ An unexpected error occurred: {e}")
