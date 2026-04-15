import yt_dlp
import os
import sys

# --- USER CONFIGURATION ---
# 1. REPLACE THIS LIST with your actual YouTube links
YOUTUBE_LINKS = [
    'https://youtu.be/OlgBYgbPQV4?si=3k_H1YsfTso1hbbL'

    # Add all your links here
]

# 2. The desired output directory
#OUTPUT_DIR = 'Generate Audio/voices/Roger Scruton'
OUTPUT_DIR = 'Generate Audio/voices/Google Books Narrators'

# ---------------------------

def download_youtube_audio_as_wav(youtube_links, output_dir):
    """
    Downloads audio from a list of YouTube links, limits the duration to 10 minutes,
    and saves them as WAV files.
    """
    # Create the output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    # yt-dlp options for best audio and conversion to WAV
    ydl_opts = {
        # ⬇️ NEW: Limit download/conversion duration to 10 minutes (00:10:00)
        # '-to' is a FFmpeg argument passed to the downloader to stop the stream
        'downloader_args': {'ffmpeg': ['-to', '00:10:00']},

        # Select best audio format
        'format': 'bestaudio/best',
        # Output template: save in the specified directory using the video title
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        # Post-processing to extract audio and convert to WAV
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',  # Convert to WAV format
            'preferredquality': '6',  # 1 - 10 (highest) quality
        }],
        'nocheckcertificate': True,
        'no_warnings': True,
        'verbose': False,
    }

    print(f"Starting download for {len(youtube_links)} links into '{output_dir}', limited to 10 minutes each...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # Loop and download all links in the list
            ydl.download(youtube_links)
            print("All requested downloads completed successfully.")
        except Exception as e:
            print(f"An error occurred during download: {e}", file=sys.stderr)


if __name__ == "__main__":
    if all('EXAMPLE_LINK' not in link for link in YOUTUBE_LINKS):
        download_youtube_audio_as_wav(YOUTUBE_LINKS, OUTPUT_DIR)
    else:
        print(
            "\n*** ERROR: Please update the YOUTUBE_LINKS list with your actual YouTube URLs before running the script. ***")