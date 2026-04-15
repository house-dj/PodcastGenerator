import os
import io
import requests
import io
import json
import time
from pydub import AudioSegment

def time_to_ms(time_val):
    """
    Converts a time value (integer seconds or 'M:S' string) to milliseconds.
    """
    if isinstance(time_val, (int, float)):
        # Treat as seconds
        return int(time_val * 1000)

    elif isinstance(time_val, str):
        # Treat as 'M:S' format (e.g., "1:30" for 1 minute 30 seconds)
        try:
            if ':' in time_val:
                minutes, seconds = map(float, time_val.split(':'))
                return int((minutes * 60 + seconds) * 1000)
            else:
                # If a string without ':' is passed, treat it as seconds
                return int(float(time_val) * 1000)
        except ValueError:
            raise ValueError(f"Invalid time format: {time_val}. Use seconds (e.g., 30) or 'M:S' (e.g., '1:30').")

    return None


def trim_mp3_seconds(input_file, trim_count=1,
                     # output_file,
                     start_time=None, end_time=None, duration=None):
    """
    Trims an MP3 file using time values in seconds or 'M:S' format.

    :param input_file: Path to the input MP3 file.
    :param trim_count: counter of the trimmed clip being requested, for case where multiple clips are requested to trim from
    the same input_file.
    :param output_file: Path for the trimmed output MP3 file.
    :param start_time: Start time (in seconds, 'M:S' string, or None).
    :param end_time: End time (in seconds, 'M:S' string, or None).
    :param duration: Duration of the clip in seconds (integer or float).
    """
    if not os.path.exists(input_file):
        print(f"Error: Input file not found at {input_file}")
        return

    try:
        # Convert all time parameters to milliseconds (ms)
        start_ms = time_to_ms(start_time) if start_time is not None else None
        end_ms = time_to_ms(end_time) if end_time is not None else None
        duration_ms = time_to_ms(duration) if duration is not None else None

        # 1. Load the audio file
        audio = AudioSegment.from_mp3(input_file)

        # 2. Determine the trimming segment
        segment_start = start_ms if start_ms is not None else 0
        segment_end = end_ms

        # Handle start + duration case
        if start_ms is not None and duration_ms is not None:
            segment_end = start_ms + duration_ms

        # Handle start and end case (standard trimming)
        elif start_ms is not None and end_ms is not None:
            if start_ms >= end_ms:
                print("Error: Start time must be less than end time.")
                return
            segment_end = end_ms

        # Handle only start time (trim to end of file)
        elif start_ms is not None:
            segment_end = len(audio)  # Length of audio in ms

        # Handle only end time (trim from start of file)
        elif end_ms is not None:
            segment_start = 0
            segment_end = end_ms

        else:
            print(
                "Error: You must provide at least a start time, an end time, or both, or a start time and a duration.")
            return

        # 3. Perform the trim and export
        trimmed_audio = audio[segment_start:segment_end]
        #trimmed_audio = AudioSegment.from_file(io.BytesIO(trimmed_audio1), format="mp3")

        print(f"Trimming from {segment_start / 1000:.2f}s to {segment_end / 1000:.2f}s.")
        #trimmed_audio.export(output_file, format="mp3")
        print(f"✅ Successfully trimmed clip number "+ str(trim_count))
        return trimmed_audio

    except Exception as e:
        print(f"❌ An error occurred during processing: {e}")
        print(
            "\n**Note:** pydub relies on FFmpeg or Libav. Ensure one is installed and accessible in your system's PATH.")

print("-" * 30)

# *** SET THE START, END, AND DURATION OF CLIPS TO TRIM HERE: ***
clipslist =     [["3:03", "92:19"] ]

print("Number of clips to extract: " + str(len(clipslist)))
audio_chunks=[]
output_file = "Generate Audio/voices/Roger Scruton/Of Beauty and Consolation Episode 2 Roger Scruton_trimmed.mp3"
for i in range(0, len(clipslist)):
    trim_clip = trim_mp3_seconds(
        "Generate Audio/voices/Roger Scruton/Of Beauty and Consolation Episode 2 Roger Scruton.mp3",
        trim_count=i+1,
        # "voices/Ioan_Gruffudd1.mp3",
        start_time=clipslist[i][0],
        end_time=clipslist[i][1]
        #, duration=clipslist[i][2]
        )
    audio_chunks.append(trim_clip)

# print("audio_chunks length: " + str(len(audio_chunks)))
if len(clipslist) > 0:
    final_audio = sum(audio_chunks)
    final_audio.export(output_file, format="mp3")
    print(f"✅ Successfully trimmed all clips and saved to file " + output_file)