import os
import glob
import sys
from pydub import AudioSegment

# --- CONFIGURATION ---
# The directory containing the WAV files
directory = 'Generate Audio/voices/Google Books Narrators'

# Max duration limit (10 minutes) in milliseconds
MAX_DURATION_MS = 10 * 60 * 1000


# IMPORTANT: If FFmpeg is not in your system's PATH, you must uncomment
# the line below and replace the path with the actual location of your
# FFmpeg executable (e.g., ffmpeg.exe).
# AudioSegment.converter = r"C:/path/to/your/ffmpeg.exe"
# ---------------------

"""
Trims all WAV files in a directory (and its subdirectories) to a 
maximum of 10 minutes, then deletes the original untrimmed file.
"""
if not os.path.exists(directory):
    print(f"Error: Directory not found: {directory}")
    # Exit the script if the directory doesn't exist
    sys.exit(1)


# Find all .wav files recursively
search_path = os.path.join(directory, '**', '*.wav')
wav_files = glob.glob(search_path, recursive=True)

if not wav_files:
    print(f"No .wav files found in '{directory}'.")
    # Exit the script if no files are found
    sys.exit(0)


print(f"Found {len(wav_files)} WAV file(s) to process in '{directory}'.")

# --- LOOP IMPLEMENTATION ---
for original_path in wav_files:
    # Define temp_path *inside* the loop for the current file
    temp_path = original_path + ".temp"

    try:
        print(f"\nProcessing: {os.path.basename(original_path)}")

        # 1. Load the WAV file
        audio = AudioSegment.from_wav(original_path)
        original_duration_ms = len(audio)

        # Check if trimming is needed
        if original_duration_ms <= MAX_DURATION_MS:
            print(f"File is already short ({original_duration_ms / 1000:.2f}s). Skipping.")
            continue # Skip to the next file in the loop


        # 2. Trim to the first 10 minutes
        trimmed_audio = audio[:MAX_DURATION_MS]
        new_duration_ms = len(trimmed_audio)
        print(f"Trimming from {original_duration_ms / 1000:.2f}s to {new_duration_ms / 1000:.2f}s (10 minutes).")

        # 3. Save the trimmed file to a temporary file
        trimmed_audio.export(temp_path, format="wav")

        # 4. Success: Delete the original file
        os.remove(original_path)

        # 5. Rename the temporary file to the original file name
        os.rename(temp_path, original_path)

        print(f"✅ Successfully trimmed and replaced original.")

    except Exception as e:
        print(f"❌ Failed to process {os.path.basename(original_path)}. Error: {e}", file=sys.stderr)
        # Cleanup any leftover temporary file
        if os.path.exists(temp_path):
            print(f"   - Cleaning up temporary file: {os.path.basename(temp_path)}", file=sys.stderr)
            try:
                os.remove(temp_path)
            except:
                pass