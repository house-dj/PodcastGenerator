# from pytube import YouTube
from pytubefix import YouTube
from pytubefix.cli import on_progress
import os
from moviepy.editor import AudioFileClip

youtube_url = "https://youtu.be/2TgFlTGcZFw?si=NnlwyaIr8jJlYqNh"
output_path= "Generate Audio/voices"
# https://youtu.be/AtHpANTpOIc?si=CJooxPMGvLGvGsol
# https://youtu.be/XAb-W8bXPas?si=vP2y_3J_esflqgBg
try:
    yt = YouTube(youtube_url, on_progress_callback = on_progress)
    audio_stream = yt.streams.filter(only_audio=True).first()

    # Download the audio stream
    downloaded_file = audio_stream.download(output_path=output_path)

    # Get the base filename and construct the new MP3 filename
    base, ext = os.path.splitext(downloaded_file)
    mp3_file = base + '.mp3'

    # Convert to MP3 using moviepy
    audio_clip = AudioFileClip(downloaded_file)
    audio_clip.write_audiofile(mp3_file)
    audio_clip.close()

    # Optionally, remove the original downloaded file
    os.remove(downloaded_file)

    print(f"Successfully converted '{yt.title}' to MP3: {mp3_file}")
except Exception as e:
    print(f"An error occurred: {e}")
