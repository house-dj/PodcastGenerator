import os
import sys

FILES_DIRECTORY = "Generate Text Scripts/generated_text_files/ssml break tags fix"
# Define the file extension to search for (e.g., '.txt')

def find_replace(text: str) -> str:
    """
    Does a find and replace on defined words in a text string.
    Args:
        text: The input text as a single string.
    Returns:
        Edited text
    """
    final_document = text

    replace_words = [
        ['INTRODUCTION','Introduction.'],
        ['OVERVIEW','Overview.'],
        ['CHRONOLOGY','Chronology.'],
        ['BRIEF CHRONOLOGY', 'Chronology.'],
        ['SECTION ', 'Part '],
        ['SYNTHESIS','Synthesis.'],
        ['REVIEW','Review.'],
        ['RECAP', 'Review.'],
        ['KEY NAMES','Key Names.'],
        ['CLOSING','Closing.'],
        ['OUTRO', 'Closing.']
        ]
    for i in range(0, len(replace_words)):
        final_document = final_document.replace(f'{replace_words[i][0]}',f'{replace_words[i][1]}')

    return final_document

if __name__ == '__main__':
    # Determine the directory to process. Use the first command-line argument
    # or a default directory name if none is provided.
    if len(sys.argv) > 1:
        target_directory = sys.argv[1]
    else:
        target_directory = FILES_DIRECTORY # Default directory name

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
                    edited_text = find_replace(document_content)

                    # 3. Write the processed content back to the original file (overwriting)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(edited_text)

                    processed_count += 1
                    print(f"  Successfully updated {filename}.")

                except Exception as e:
                    print(f"  Failed to process {filename}: {e}")

    print(f"\nFind and Replace processing complete. Total files updated: {processed_count}")