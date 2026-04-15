from pydub import AudioSegment
AudioSegment.converter = r"C:/ffmpeg/ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe"

wavfile = "Generate Audio/voices/Male Chinese_William Han_Master of Demon Gorge_2.wav"
mp3file = "Generate Audio/voices/Master of Demon Gorge.mp3"

# Load the MP# file
audio = AudioSegment.from_mp3(mp3file)
# Export as WAV
audio.export(wavfile, format="wav", bitrate="48k")
print(f"WAV conversion complete: {wavfile}")
