import os
import wave
from google import genai
from google.genai import types
from utility_wav_to_mp3 import wavtomp3

# --- Configuration ---
INPUT_TEXT_FILE = "out/TEST_SCRIPT.txt"
OUTPUT_WAV_FILE = "TEST_AUDIO.wav"
OUTPUT_MP3_FILE = "TEST_AUDIO.mp3"
# The specialized TTS model
TTS_MODEL = "gemini-2.5-flash-preview-tts"
MAX_CHARS_PER_CALL = 9000 # The confirmed API limit
api_key = os.getenv("GEMINI_API_KEY")

import re


def split_text_at_sentence_ends(text: str, max_chars: int = 9000) -> list[str]:
    """
    Splits a large block of text into chunks, ensuring:
    1. No chunk exceeds the max_chars limit.
    2. Splits occur only at sentence-ending punctuation (., ?, !).
    """
    if not text:
        return []

    # Regex to find sentence boundaries (., ?, ! followed by a space or end of string)
    # The parentheses around the punctuation allow it to be included in the split result.
    sentence_delimiters = r'([.?!])\s+'

    # Split the text into sentences (includes the delimiter and the space after)
    # The re.split() behavior ensures the delimiters are captured.
    # The strip() on each piece is essential for cleaning up leading/trailing whitespace.
    sentences = [piece.strip() for piece in re.split(sentence_delimiters, text) if piece.strip()]

    # Since re.split(r'([.?!])\s+', text) returns the delimiter separately,
    # we need to re-pair the sentences and their punctuation.
    chunks = []
    current_chunk = ""

    # Iterate in steps of 2: sentence text and then its delimiter/space
    for i in range(0, len(sentences), 2):
        sentence_text = sentences[i]

        # Check if we have a delimiter (it might be missing for the very last piece)
        delimiter = sentences[i + 1] if i + 1 < len(sentences) else ""

        # Combine the sentence and its delimiter to form the full sentence
        full_sentence = f"{sentence_text}{delimiter} " if delimiter else sentence_text

        # 1. Check if adding the new sentence exceeds the limit
        if len(current_chunk) + len(full_sentence) > max_chars and current_chunk:
            # Current chunk is full, start a new one
            chunks.append(current_chunk.strip())
            current_chunk = ""

        # 2. Handle a single sentence that is ALREADY too long (though rare)
        if len(full_sentence) > max_chars:
            # In a production environment, you might need a more complex fallback,
            # but here, we just split at a fixed length as a last resort.
            print(f"⚠️ Warning: Sentence too long ({len(full_sentence)} chars). Splitting mid-sentence.")
            # For simplicity, we just add it as its own chunk, assuming the API might handle it,
            # but ideally, this would use a fallback character-level split.
            chunks.append(full_sentence.strip())
            current_chunk = ""  # Ensure we start fresh after the oversized chunk
        else:
            # Add the sentence to the current chunk
            current_chunk += full_sentence

    # 3. Add the last remaining chunk
    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

def save_pcm_to_wav(filename: str, pcm_data: bytes, channels=1, rate=24000, sample_width=2):
    """Utility to save raw PCM audio data received from the API as a standard WAV file."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_data)

def generate_speech_from_text_file():
    """Reads text, splits it into logical chunks, calls the Gemini TTS model for each, and saves the audio."""
    print("Starting Text-to-Speech generation...")

    try:
        # 1. Read text from the local file
        with open(INPUT_TEXT_FILE, 'r', encoding='utf-8') as f:
            text_to_speak = f.read()

        if not text_to_speak.strip():
            print(f"🛑 Error: The file '{INPUT_TEXT_FILE}' is empty. Add some text to it.")
            return

        # 2. Split the text into logical chunks
        print(f"Total input characters: {len(text_to_speak)}")
        text_chunks = split_text_at_sentence_ends(text_to_speak, MAX_CHARS_PER_CALL)
        print(f"Text split into {len(text_chunks)} chunk(s) for submission.")

        # Prepare for saving all audio pieces
        all_pcm_data = b""

        # 3. Process each chunk
        for i, chunk in enumerate(text_chunks):
            print(f"--- Processing Chunk {i + 1}/{len(text_chunks)} ({len(chunk)} characters) ---")

            # Initialize the Gemini Client on the first iteration or outside the loop
            # (It's generally better to initialize the client once)
            if i == 0:
                client = genai.Client(api_key=api_key)

            # Call the TTS model
            # print(chunk)
            prompted_chunk = f"Please read the following text with a clear British accent, and be sure to pause at the SSML break tags for the number of seconds specified: {chunk}"
            response = client.models.generate_content(
                model=TTS_MODEL,
                contents=prompted_chunk,
                config=types.GenerateContentConfig(
                    # system_instruction="",
                    # system_instruction="The narrator should adopt a neutral, clear English voice with a UK (British) accent.",
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name='Achird'
                            )
                        )
                    )
                )
            )

            # Extract the raw PCM audio data (bytes)
            try:
                pcm_data = response.candidates[0].content.parts[0].inline_data.data
                all_pcm_data += pcm_data
            except Exception as e:
                print(f"🛑 Error extracting audio for Chunk {i + 1}: {e}")
                # Decide if you want to continue or break on error

        # 4. Convert and save the final concatenated audio as a single WAV file and then convert to MP3
        if all_pcm_data:
            save_pcm_to_wav(OUTPUT_WAV_FILE, all_pcm_data)
            print(f"\n✅ Success! All {len(text_chunks)} chunks were concatenated and saved to: {OUTPUT_WAV_FILE}")
            wavtomp3(OUTPUT_WAV_FILE, OUTPUT_MP3_FILE)

    except FileNotFoundError:
        print(f"🛑 Error: Input file '{INPUT_TEXT_FILE}' not found. Please create it.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Make sure to include the split_text_at_sentence_ends function definition above this call
    generate_speech_from_text_file()