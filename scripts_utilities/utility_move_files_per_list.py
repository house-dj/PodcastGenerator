import os
import shutil

# The file containing the list of files to move
LIST_FILE = "Generate Text Scripts\generated_text_files\scripts_under_sent_length_to_remove.txt"

# The directory to move the files into
TARGET_DIR = "Generate Text Scripts\generated_text_files\scripts_removed_low_sentence_length"
SOURCE_DIR = "Generate Text Scripts\generated_text_files"


def move_files_from_list(list_filepath: str, target_directory: str, source_directory: str = '.'):
    """
    Reads a list of filenames from a file and moves them from the source directory
    to the target directory.

    Args:
        list_filepath: Path to the file containing the list of filenames (one per line).
        target_directory: The name of the directory to move the files into.
        source_directory: The directory where the files currently reside (defaults to current directory).
    """
    # 1. Create the target directory if it doesn't exist
    try:
        if not os.path.exists(target_directory):
            os.makedirs(target_directory)
            print(f"Created target directory: {target_directory}")
        else:
            print(f"Target directory already exists: {target_directory}")
    except OSError as e:
        print(f"Error creating directory {target_directory}: {e}")
        return

    # 2. Read the list of files to move
    files_to_move = []
    try:
        with open(list_filepath, 'r', encoding='utf-8') as f:
            # Read lines and strip whitespace/newlines from each line
            files_to_move = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: List file not found at '{list_filepath}'. Cannot proceed.")
        return
    except Exception as e:
        print(f"Error reading list file: {e}")
        return

    # 3. Process the file movement
    moved_count = 0
    skipped_count = 0

    print(f"\nAttempting to move {len(files_to_move)} files...")

    for filename in files_to_move:
        source_path = os.path.join(source_directory, filename)
        destination_path = os.path.join(target_directory, filename)

        if os.path.exists(source_path):
            try:
                # Use shutil.move for atomic file movement
                shutil.move(source_path, destination_path)
                print(f"  Moved: {filename}")
                moved_count += 1
            except Exception as e:
                print(f"  FAILED to move {filename}: {e}")
                skipped_count += 1
        else:
            print(f"  SKIPPED: {filename} (File not found in {source_directory})")
            skipped_count += 1

    # 4. Final summary
    print("\n--- Summary ---")
    print(f"Total files listed: {len(files_to_move)}")
    print(f"Successfully moved: {moved_count}")
    print(f"Files skipped/failed: {skipped_count}")


if __name__ == '__main__':
    # 'source_directory' defaults to '.' (the directory where this script is run)
    move_files_from_list(LIST_FILE, TARGET_DIR, SOURCE_DIR)