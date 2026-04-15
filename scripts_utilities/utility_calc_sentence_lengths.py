import re
import csv
import os
from typing import Tuple, List

FILES_DIRECTORY = "Generate Text Scripts/generated_text_files/length checking dir"

# Define the name of the output CSV file
OUTPUT_CSV_FILENAME = "Generate Text Scripts/generated_text_files/sentence_length_results.csv"
# Define the file extension to search for (e.g., '.txt')
FILE_EXTENSION = '.txt'


def analyze_sentence_length(text: str) -> Tuple[int, int, float]:
    """
    Analyzes a block of text to determine the total sentences, total words,
    and the average sentence length.

    Args:
        text: The input text as a single string.

    Returns:
        A tuple containing (total_sentences, total_words, average_length).
    """

    # 1. Block Removal: Remove text between 'Chronology.' and 'Part 1' (inclusive)
    # The 's' flag (re.DOTALL) allows '.' to match newlines.
    # The '?' makes the matching non-greedy, stopping at the first 'Part 1'.
    text_without_chronology = re.sub(
        r'Chronology\..*?Part 1',
        ' ',  # Replace the whole block with a space
        text,
        flags=re.DOTALL
    )

    # 2. Block Removal: Remove text between 'Key Names.' and 'Closing' (inclusive)
    text_without_key_names = re.sub(
        r'Key Names\..*?Closing',
        ' ',  # Replace the whole block with a space
        text_without_chronology,
        flags=re.DOTALL
    )

    # Pre-processing step: Remove all SSML tags (e.g., <break time="100ms"/>)
    # This pattern matches any text inside angle brackets, which covers most XML/HTML/SSML tags.
    # We replace them with a single space to prevent words from merging (e.g., "word<tag>word" -> "word word").
    cleaned_text = re.sub(r'<[^>]+>', ' ', text)

    # 1. Sentence Tokenization (counting sentences)
    # This pattern splits sentences based on punctuation followed by whitespace,
    # and handles common sentence-ending marks (. ! ?)
    # Note: This is a simple tokenizer. More complex scenarios (e.g., abbreviations)
    # would require an NLP library like NLTK or spaCy.
    sentences = re.split(r'[.!?]+\s', cleaned_text.strip())

    # Filter out empty strings that might result from trailing punctuation
    valid_sentences = [s for s in sentences if s]
    total_sentences = len(valid_sentences)

    if total_sentences == 0:
        return 0, 0, 0.0

    total_words = 0

    # 2. Word Tokenization (counting words)
    for sentence in valid_sentences:
        # Simple word count: split by any non-word characters and filter empty results
        # A "word" is defined here as any sequence of letters, numbers, or hyphens.
        words = re.findall(r'\b\w+\b', sentence.lower())
        total_words += len(words)

    # 3. Calculate average
    average_length = total_words / total_sentences if total_sentences > 0 else 0.0

    return total_sentences, total_words, average_length


def process_directory_and_output_csv(directory_path: str = '.', output_file: str = OUTPUT_CSV_FILENAME):
    """
    Scans a directory for text files, calculates the average sentence length
    for each, and writes the results to a CSV file.

    Args:
        directory_path: The path to the directory to scan (default is current directory).
        output_file: The name of the CSV file to write the results to.
    """
    results: List[List[str | float]] = []

    # Headers for the CSV file
    results.append(['File Name', 'Total Sentences', 'Total Words', 'Average Sentence Length (Words)'])

    print(f"Scanning directory: {os.path.abspath(directory_path)} for *{FILE_EXTENSION} files...")

    for filename in os.listdir(directory_path):
        if filename.endswith(FILE_EXTENSION):
            filepath = os.path.join(directory_path, filename)

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    text_content = f.read()

                # Analyze the content
                total_sentences, total_words, avg_length = analyze_sentence_length(text_content)

                # Add result to the list
                results.append([
                    filename,
                    total_sentences,
                    total_words,
                    round(avg_length, 2)  # Round to two decimal places
                ])
                print(f"Analyzed {filename}: {total_sentences} sentences, Avg. Length: {avg_length:.2f}")

            except Exception as e:
                print(f"Could not process file {filename}. Error: {e}")

    # Write all results to the CSV file
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(results)
        print(f"\n--- SUCCESS ---")
        print(f"Results written to '{os.path.abspath(output_file)}'")
    except Exception as e:
        print(f"Error writing to CSV file: {e}")


if __name__ == '__main__':
    # You can change '.' to any path you want to scan, e.g., 'C:/Users/Documents/Texts'
    process_directory_and_output_csv(directory_path=FILES_DIRECTORY)