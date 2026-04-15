from pydub import AudioSegment
AudioSegment.converter = r"C:/ffmpeg/ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe"

wavfile='Generate Audio/audio_files/126_American Hemisphere Pre-Columbian Americas circa 1500 BCE to 1500 CE 20251118-142211+0800_PART_2.wav'
mp3file='Generate Audio/audio_files/126_American Hemisphere Pre-Columbian Americas circa 1500 BCE to 1500 CE 20251118-142211+0800_PART_2.mp3'
# Load the WAV file
audio = AudioSegment.from_wav(wavfile)
# Export as MP3
audio.export(mp3file, format="mp3", bitrate="48k")
print(f"MP3 conversion complete: {mp3file}")
