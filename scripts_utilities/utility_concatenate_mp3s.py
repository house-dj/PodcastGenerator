import os
import subprocess
import glob

# --- Configuration ---
# Set the directory where your MP3 files are located.
# Use '.' for the current directory where the script is run.
directory = 'Generate Audio/audio_files/tem'
output_file = "Generate Audio/audio_files/126_American Hemisphere Pre-Columbian Americas circa 1500 BCE to 1500 CE 20251118-142211+0800.mp3"
TEMP_LIST_FILE = "mp3_list_temp.txt"

"""
Finds all MP3 files in a directory, sorts them by filename,
and uses FFmpeg's 'concat' demuxer to join them into a single file.

Args:
    directory: The path to the folder containing the MP3s.
    output_file: The name of the final merged MP3 file.
"""
print(f"Searching for MP3 files in: {os.path.abspath(directory)}")

# 1. Get all MP3 files and sort them by filename (alphabetical/numerical order)
# The glob module is used to find all files ending in .mp3
mp3_files = sorted(glob.glob(os.path.join(directory, '*.mp3')))

if not mp3_files:
    print("❌ Error: No MP3 files found in the specified directory.")

print(f"Found {len(mp3_files)} files. Concatenation order (by filename):")
for file in mp3_files:
    print(f"  - {os.path.basename(file)}")

# 2. Create the temporary list file for FFmpeg's concat demuxer
# FFmpeg requires paths to be escaped and preceded by 'file '
try:
    with open(TEMP_LIST_FILE, 'w', encoding='utf-8') as f:
        for mp3_file in mp3_files:
            # Use os.path.abspath to ensure absolute paths for -safe 0 flag usage
            # Paths must be enclosed in single quotes if they contain spaces
            safe_path = os.path.abspath(mp3_file).replace('\\', '/')  # FFmpeg prefers forward slashes
            f.write(f"file '{safe_path}'\n")

    # 3. Define and execute the FFmpeg command
    ffmpeg_command = [
        'ffmpeg',
        '-f', 'concat',  # Use the concat demuxer
        '-safe', '0',  # Required when using absolute paths
        '-i', TEMP_LIST_FILE,  # Specify the list file as the input
        '-c', 'copy',  # Stream copy (lossless concatenation)
        output_file  # Specify the output file name
    ]

    print("\nExecuting FFmpeg command...")
    # Run the command and capture output/errors
    subprocess.run(ffmpeg_command, check=True)

    print(f"\n✅ Success! Files concatenated to **{output_file}**")

except FileNotFoundError:
    print("\n❌ Error: FFmpeg command not found.")
    print("Please ensure FFmpeg is installed and added to your system's PATH.")
except subprocess.CalledProcessError as e:
    print(f"\n❌ Error during FFmpeg execution:\n{e}")
finally:
    # 4. Clean up the temporary list file
    if os.path.exists(TEMP_LIST_FILE):
        os.remove(TEMP_LIST_FILE)
        print(f"Cleaned up temporary file: {TEMP_LIST_FILE}")
