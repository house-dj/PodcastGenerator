import re
import os
import sys
import csv
import argparse

YEARS_LOOKUP_FILENAME = "Generate Text Scripts/reference files/year_spoken_lookup.csv"
BREAK_TAG_SHORT = '<break time="0.5s"/>'
BREAK_TAG_MEDIUM= '<break time="0.9s"/>'

def process_document_for_ssml(document_text, break_tag_short=BREAK_TAG_SHORT, break_tag_medium= BREAK_TAG_MEDIUM):
    """
    Inserts a <break time="0.5s"/> tag into text based on complex,
    paragraph-specific rules, and applies global replacements for colons and semicolons.

    The rules are:
    1. Break tag between each sentence in the first paragraph (Introduction).
    2. Break tag after the first sentence in every paragraph *other* than the first.
    3. Break tag before the last sentence of the second paragraph (Overview).
    4. Break tag at each paragraph break (which we will define as two newlines).
    5. Break tag before last sentence of a paragraph if paragraph has 9 or more sentences
    6. Global: Break tag after every colon ':' or semi-colon ';'.
    7. Global cleanup: Check for occurrences of double-break tags and replace with a single tag.

    Args:
        document_text (str): The raw text content of the document.

    Returns:
        str: The document text with SSML break tags inserted.
        :param break_tag_medium:
        :param document_text:
        :param break_tag_short:
    """

    warning = "" # default value, no warning

    # First add any missing full stops after Part X section headings. This is needed in the final corrections.
    document_text = re.sub(r'<break time="2s"/>\s*(Part.+)\n', r'<break time="2s"/>\n\1.\n', document_text)
    # Remove double full-stops resulting from above
    document_text = document_text.replace(f'..',f'.')
    document_text = document_text.replace(f'. .', f'.')
    # Special case remove full stops after 'St.' and verbalise
    document_text = document_text.replace('St.', 'Saint ')

    # Replace the full stops after single letters, e.g. in initials like Ulysses S. Grant, with a space.
    # this seems to work in UI TTS testing, e.g. W.E.B. to W E B
    document_text = re.sub(r'([A-Z])\.', r'\1 ', document_text)

    # 1. Remove potential existing SSML break tags and excessive whitespace
    text_cleaned = re.sub(r'</?\s*break\s+[^>]*/>', '', document_text, flags=re.I)
    # text_cleaned = re.sub(BREAK_TAG, '', document_text, flags=re.I)  # *** UPDATED

    # --- Standardize Paragraph Breaks FIRST (CRITICAL FOR LINE BREAKS) ---
    # Convert all varying sequences of newlines/spaces into a standard \n\n separator.
    text_cleaned = re.sub(r'\s*\n\s*\n\s*', '****', text_cleaned.strip())

   # Split the document into paragraphs based on the standard two-newline separator
    paragraphs = text_cleaned.split('****')
    # print("Paragraphs split count: " + str(len(paragraphs)))
    processed_paragraphs = []

    # Regex to split text into sentences based on common terminators,
    # while preserving the terminator and handling common abbreviations (like "BCE" or "Dr.").
    # NOTE: Since Rule 5 already added breaks after semi-colons, we only focus on .?! here for sentence structure.
    # sentence_splitter = re.compile(r'([.?!])\s+(?=[A-Z0-9\"\'\u201c\u2018])')
    sentence_splitter = re.compile(r'([.?!])\s*')

    intro_paragraph_first = None # intialise

    # Identify the paragraphs in the Introduction
    for i, paragraph_text in enumerate(paragraphs):
        if paragraph_text[:12]=='Introduction':
            #print("found introduction first")
            intro_paragraph_first = i
        elif paragraph_text[:8]=='Overview':
            #print("found introduction last")
            intro_paragraph_last = i-1
        else:
            continue

    if intro_paragraph_first is None: # Introduction was not found, use default values and warn
        intro_paragraph_first = 1
        intro_paragraph_last = 2
        warning = "SSML insertion warning: Intro paragraph not found, defaulting as second paragraph."

    # Main loop to apply rules 1 to 5
    for i, paragraph_text in enumerate(paragraphs):
        #print("Main loop counter: " + str(i))
        # Skip empty paragraphs that might result from splitting
        if not paragraph_text.strip():
            #print("empty paragraph skipped")
            continue

        # --- Handle Paragraph Heading Break (Logic Simplified) ---
        # The standardized splitting ensures headings are usually the start of the paragraph.
        # We rely on the sentence splitter/joiner below, combined with the final cleanup,
        # to ensure the break is there. We've removed the complex header logic as it was unstable.

        # Split the current paragraph into sentences
        sentences = sentence_splitter.split(paragraph_text)
        #print("sentences split")
        # The split operation above returns the sentence content and the punctuation mark separately.
        # We need to re-group them.
        re_grouped_sentences = []
        current_sentence = ""
        for part in sentences:
            current_sentence += part
            # If the part is a punctuation mark, we finalize the sentence.
            if part in ['.', '?', '!']:
                re_grouped_sentences.append(current_sentence.strip())
                #print(current_sentence[:12])
                current_sentence = ""
                #print("Re-grouped sentence added")

        """
        # Commenting out this condition as seems headings are not being treated as separate to the paragraphs
        if len(re_grouped_sentences) == 1: # single sentence paragraph is a heading or can be skipped.
            text = ' '.join(re_grouped_sentences)
            #re_grouped_sentences.append("****Start Single Sentence Para***") # DEBUG
            processed_paragraphs.append(text)  # join it to list of paragraphs and move on
            print("Single Sentence paragraph")
            continue
        """
        """
        # *** Seems this won't work and is redundant anyway ***
        # Append any remaining text (including potential text after the last sentence or a sentence not ending with standard punctuation)
        if current_sentence.strip():
            re_grouped_sentences.append(current_sentence.strip())
        """

        # --- Apply Paragraph-Specific Rules 1, 2, 3 ---

        if i>= intro_paragraph_first and i <= intro_paragraph_last:  # Introduction is the second paragraph
            # Rule 1: Break tag between each sentence in the first paragraph (Introduction).
            processed_paragraph = break_tag_short.join(re_grouped_sentences)
            #processed_paragraph = processed_paragraph + " ****End Intro Paras***"  # DEBUG
            # print("Intro paragraphs done")
        elif i == intro_paragraph_last + 1: # this is the Overview paragraph
            if len(re_grouped_sentences) >= 2:
                # Rule 2: Break tag after the first sentence (which is not the section heading)
                # Rule 3: Break tag before the last sentence.

                first_sentence = re_grouped_sentences[0] # Need to store this section heading to append below
                second_sentence = re_grouped_sentences[1] # Adjusted to second sentence as first is section heading.
                last_sentence = re_grouped_sentences[-1]
                middle_sentences = re_grouped_sentences[2:-1]
                parts = []
                # Apply Rule 2: Add break after the first sentence
                parts.append(first_sentence + break_tag_short + second_sentence + break_tag_medium)
                # Join middle sentences normally (if any)
                parts.extend(middle_sentences)
                # Apply Rule 3: Add break before the last sentence
                if middle_sentences:
                    parts.append(break_tag_short + last_sentence)
                else:
                    parts.append(break_tag_short + last_sentence)
                processed_paragraph = " ".join(parts)
            else:
                # If there's only one sentence, just apply Rule 2 (after the first sentence)
                processed_paragraph = re_grouped_sentences[0] + break_tag_medium
            #processed_paragraph = processed_paragraph + " ****End Para (OVERVIEW)***"  # DEBUG
            # print("Second paragraph done") # Debug
        else: # every other paragraph apart from Introduction and Overviews
            # Rule 2: Break tag after the first sentence.
            if len(re_grouped_sentences) >= 2: # check para has more than one sentence
                first_sentence = re_grouped_sentences[0]
                remaining_text = " ".join(re_grouped_sentences[1:])
                # check if first sentence is a Part section header
                if re.search(r'(Part\s\d)',first_sentence) or \
                re.search(r'(Synthesis and Review)', first_sentence) or \
                re.search(r'(Key Names)',first_sentence) or\
                re.search(r'(Key Names, Places, Events, Things)', first_sentence) or\
                re.search(r'(Closing)', first_sentence):
                    # skip section header by merging with next sentence
                    first_sentence = re_grouped_sentences[0] + break_tag_medium + "\n " + re_grouped_sentences[1]
                    remaining_text = " ".join(re_grouped_sentences[2:])
                # Rule 5 if 6 or more sentences then break before last
                if len(re_grouped_sentences) >= 6:
                    parts = []
                    # Apply Rule 2 and Rule 5
                    last_sentence = re_grouped_sentences[-1]
                    middle_text = re_grouped_sentences[2:-1]
                    parts.append(first_sentence + break_tag_medium)
                    parts.extend(middle_text)
                    parts.append(break_tag_short + last_sentence)
                    processed_paragraph = " ".join(parts)
                else:
                    # Apply Rule 2
                    processed_paragraph = first_sentence + break_tag_medium + " " + remaining_text
                #processed_paragraph = processed_paragraph  + " ****End ANOTHER Para***"  # DEBUG
                #print("Other paragraph done") # Debug
            else:
                # If there's only one sentence, just apply Rule 2 (after the first sentence)
                processed_paragraph = re_grouped_sentences[0] + break_tag_medium
        processed_paragraphs.append(processed_paragraph.strip())
        #print("Paragraphs appended") # DEBUG

    # print("processed_paragraphs length: " + str(len(processed_paragraphs)))

    # Rule 4: Break tag at each paragraph break (joining paragraphs with a break)
    # This separation logic is now simplified and guaranteed to maintain newlines.
    separator = f'\n\n{break_tag_medium}'
    final_document = separator.join(processed_paragraphs)

    # Strip any leading separator content that might result from the join (Rule 4 is now integrated)
    # final_document = final_document.lstrip('\n').lstrip(BREAK_TAG).lstrip('\n') *** TEMP COMMENT OUT

    # --- Apply Global Rule 7: Replace double-break tags with a single tag ---
    # This catches cases where rules overlapped.
    double_break_pattern = re.escape(break_tag_short) + r'\s*' + re.escape(break_tag_short) + r'+'
    final_document = re.sub(double_break_pattern, break_tag_short, final_document, flags=re.I)
    #double_break_pattern = re.escape(BREAK_TAG) + r'\n' + re.escape(BREAK_TAG) + r'+'
    #final_document = re.sub(double_break_pattern, BREAK_TAG, final_document, flags=re.I)

    # --- Apply Global Rule 6: Break after colons and semicolons ---
    # Ensure any space OR newline after the punctuation is captured and the BREAK_TAG is inserted.
    # The replacement preserves what follows the punctuation (e.g., a space or newline).
    # We replace ':', ';', or '.' followed by optional whitespace with the punctuation + BREAK_TAG + a single space.
    final_document = re.sub(r'([:;])\s*', r'\1' + break_tag_short + ' ', final_document)

    # Clean up any potential extra spaces around the break tag
    final_document = re.sub(r'\s' + re.escape(break_tag_short) + r'\s', break_tag_short, final_document)

    # --- Extended Break Before Headings ---
    # find and replace section headers like <break time="0.5s"/>INTRODUCTION with <break time="2s"/>INTRODUCTION plus
    # line breaks around headings for clarity
    headings_list = ['Introduction.', 'Overview.','Chronology.','Brief Chronology.','Synthesis.','Review.','Synthesis and Review.',
                     'Key Names.', 'Key Names, Places, Events, Things.','Closing.']
    for i in range(0, len(headings_list)):
        final_document = final_document.replace(f'{break_tag_medium}{headings_list[i]}',f'<break time="2s"/>\n{headings_list[i]}\n')

    # Handle Part section headings separately. Note we detect Part heading text up to full stop and following break tag
    final_document = re.sub(r'<break time=".*?s"/>\s*(Part.+\.)<break time=".*?s"/>',
                            r'<break time="2s"/>\n\1<break time="0.5s"/>\n', final_document)

    # --- Add opening break to start of each file ---
    final_document = '<break time="2s"/>\n' + final_document

    # Restore the full stops after single letters e.g. in initials Ulysses S. Grant
    # final_document= re.sub(r'([A-Z])XXXX', r'\1.', final_document) # we now just sub in a permanent space see above

    return final_document, warning


def replace_years_in_text(text: str,year_map_file=YEARS_LOOKUP_FILENAME) -> tuple[str, str]:
    """
    Searches for occurrences of numeric years in the text and replaces them
    with their spoken form using the provided lookup map.
    It uses regular expressions with word boundaries (\\b) to ensure that
    only whole, isolated years are replaced (e.g., '1999' is replaced, but not
    '19990' or '21999').
    First loads the year conversion lookup table from a CSV file. The CSV is expected to have two columns: 'year_numeric' and 'year_spoken'.

    Args:
        year_map_file: The path to the CSV file (e.g., 'year_spoken_lookup.csv').
        text: The input text document as a single string.

    Returns:
        The text with all found numeric years replaced by their spoken form.
    """
    warning = "" # default value, not warning
    year_map = {}
    #print(f"Loading lookup data from: {year_map_file}")
    try:
        with open(year_map_file, mode='r', newline='', encoding='utf-8') as file:
            # We use csv.DictReader to easily access columns by name
            reader = csv.DictReader(file)
            for row in reader:
                numeric_year = row.get('year_numeric')
                spoken_year = row.get('year_spoken')

                # Basic validation: ensure both fields exist and are non-empty
                if numeric_year and spoken_year:
                    # Store the map: '1999' -> 'Nineteen ninety-nine'
                    year_map[numeric_year.strip()] = spoken_year.strip()
        #print(f"Successfully loaded {len(year_map)} year entries.")
    except FileNotFoundError:
        warning = f"Error: Lookup file not found at '{year_map_file}'. Please ensure it is uploaded."
    except Exception as e:
        warning = f"An error occurred during file processing: {e}"

    if not year_map:
        warning = "Years Replacement Warning: Year lookup map is empty. No replacements made."
        return text, warning

    # Sort the keys (years) by length in descending order and then numerically.
    # This is a good practice for replacement to ensure a longer string (e.g., '1999')
    # is checked before a substring, although for years of fixed length 3/4 it's less critical.
    # For this specific task (3- and 4-digit years), it doesn't strictly matter
    # but maintaining a sorted order is useful for other regex substitution tasks.
    sorted_years = sorted(year_map.keys(), key=lambda y: (-len(y), y), reverse=True)

    # 1. Create a single, optimized regular expression pattern
    # The pattern looks like: \b(101|102|...|1999)\b
    # \b ensures a word boundary (e.g., space, punctuation, start/end of string)
    year_pattern = r'\b(' + '|'.join(re.escape(year) for year in sorted_years) + r')\b'

    # 2. Define the replacement function for re.sub
    def replacer(match):
        # match.group(0) is the full match (e.g., '1999')
        # We look up the match in our map and return the spoken form.
        return year_map.get(match.group(0), match.group(0))

    # 3. Perform the substitution
    replaced_text = re.sub(year_pattern, replacer, text)
    return replaced_text, warning


if __name__ == '__main__':
    # Determine the directory to process. Use the first command-line argument
    # or a default directory name if none is provided.
    if len(sys.argv) > 1:
        target_directory = sys.argv[1]
    else:
        #target_directory = 'Generate Text Scripts/generated_text_files/ssml break tags fix' # Default directory name
        target_directory = 'Generate Text Scripts/generated_text_files/failed_ssml_fix_TBC'  # Default directory name

    if not os.path.isdir(target_directory):
        print(f"Error: Directory '{target_directory}' not found.")
        sys.exit(1)

    print(f"Starting scripts correction in directory: {target_directory}")
    processed_count = 0

    # Walk through the directory (including subdirectories)
    for dirpath, dirnames, filenames in os.walk(target_directory):
        for filename in filenames:
            # Only process files that look like text documents (e.g., .txt, .md, .html)
            if filename.lower().endswith(('.txt', '.md', '.html', '.script')):
                file_path = os.path.join(dirpath, filename)
                print(f"  Processing {file_path}...")

                try:
                    # 1. Read the document content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        document_content = f.read()

                    # 2. SSML processing
                    ssml_processed_content = process_document_for_ssml(document_content, BREAK_TAG_SHORT)
                    # 3. Year replacement
                    year_converted_content = replace_years_in_text(ssml_processed_content)

                    # 3. Write the processed content back to the original file (overwriting)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(year_converted_content)

                    processed_count += 1
                    print(f"  Successfully updated {filename}.")

                except Exception as e:
                    print(f"  Failed to process {filename}: {e}")

    print(f"\nProcessing complete. Total files updated: {processed_count}")