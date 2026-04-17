import os
import re
import sys
from typing import Any
import requests
import requests.exceptions
import shutil
import time
import concurrent.futures
from openrouter.types.basemodel import Unset
from pydub import AudioSegment
import base64
import io
from sanitext.text_sanitization import (
    sanitize_text
)
from openrouter import OpenRouter

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
#REWRITE_MODEL = "gemini-2.5-flash"
MAX_LLM_REWRITES = 2 # Only one rewrite attempt allowed

REWRITE_SYSTEM_PROMPT = (
    "You are an expert text cleanser and audio script writer. Your task is to minimally "
    "rewrite a short passage of text that has repeatedly failed a Text-to-Speech (TTS) API. "
    "The failure is likely due to long sentences, invisible characters, complex punctuation, "
    "long latinate words, or unusual phrasing/tags. "
    "Rewrite the text to be 20% shorter and compatible with a strict TTS engine. "
    "Maintain the original meaning and structure, but eliminate any potential complexity. "
    "Use shorter sentences up to 20 words long."
    "Maintain SSML tags as-is. "
    "Use spoken format ('eighteen forty-two') for years. Render monarchs as 'the Second', 'the Third'."
    "DO NOT ADD NEW LINES or HTML or new SSML. Output ONLY the clean, rewritten text."
)

# --- Configuration ---

# **REQUIRED: SET YOUR RESEMBLE.AI UUIDS AND API KEY**
RESEMBLEAI_API_KEY = os.getenv("RESEMBLEAI_API_KEY")

# Set these variables to your specific Resemble.AI Project and Voice UUIDs
PROJECT_UUID = "2deaeb0e"# Project 1.  Default project: "57f17ce4"
VOICE_UUID =  "d79a5198" # Charles "f4da4639" # Matt Weller native # "3c36d67d"  #'Harry Robinson' native voice  # "a644d1f" # William Han Pro # "cd324781" #Dan Wang  # "10221f18" #William Han1 #
# #"47dba11a" # African1 #"ee4d467f" #William Han
# "bacaa7b6" #Nei; Nunes #"5cc3c699" # Nigel Patterson
# #"e259d926" # Cornell Womack #"6e47d075" # David Colacci
# "526700f1" # LJ Ganser #"7e9228ec" # Joel Richards # "b4464e87" # James Adams
# #"354f199d" # Julian Elfer # "b5d19374" # Nigel Patterson
# "aa07c4a3" # Richard Davidson # "d3d0a1d9" #Saul Reichlin # "da1e9669" # Mike Duncan
# "fc5fdae3" #Derek Perkins 2. # "3c36d67d"  #'Harry Robinson' native voice  #
# "912a6238" # Saul Reichlin .  "b147125d" # Kenneth Clarke.
# "babf5809" # Derek Perkins.  "ef8c1a6d": Julian Elfer.  "f9f11022": Phylidda Nash

# 4e228dba # Adam Lofbomm native
# f4da4639 # Matt Weller native
# 2570000e # Justin (meditative) native

# Identifier of preset to alter temp, pace, etc:
PRESET_UUID = "c1480e47-0ee2-49fe-8065-6b8d33759455" # temp 1.0, pace 0.96 exaggeration 0.6
# "8fbe5efd-9e5f-422a-aa28-0591695adfe0" # temp 1.0, pace 0.95
#"6668a132-e1d6-4e46-8ebe-109062b0f1d6"  # temp 1.0

OUTPUTS_DIR = os.path.join(os.getenv('PODCAST_GENERATOR_DIR'), "audio generation files")
PODCAST_FILES_DIR = os.getenv('PODCAST_FILES_DIR')
# Directory configuration (Using the paths from your uploaded file)
QUEUED_SCRIPTS_DIR = os.path.join(OUTPUTS_DIR, "queued_scripts")
PROCESSED_SCRIPTS_DIR = os.path.join(OUTPUTS_DIR, "processed_scripts")
OUTPUT_AUDIO_DIR = os.path.join(OUTPUTS_DIR, "audio_files")
INCOMPLETE_AUDIO_DIR = os.path.join(OUTPUTS_DIR, "incomplete_audio_files")
PODCAST_QUEUE_DIR = os.path.join(PODCAST_FILES_DIR,"Podcast Feeds","Private-Podcasts","_new_uploads")

# Resemble Enhanced TTS models have a limit of 1000 characters.
MAX_CHARS_PER_CALL = 800 #960

# Retry Logic Configuration
MAX_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 2

# Parallel Processing Configuration
MAX_WORKER_THREADS = 10  # 10 simultaneous threads for I/O-bound tasks

# **NEW EXECUTION CONTROL CONSTANTS**
SEQUENTIAL_START_CHUNKS = 3  ## Process this number of chunks one-by-one first for stability and to detect any API service
# problems early
PARALLEL_LOOK_AHEAD = 10 # Only launch up to this many chunks ahead of the last successful one, to avoid wasted processing
# in the event an earlier chunk fails


# Global Configuration for incomplete file detection
INCOMPLETE_CHUNK_PATTERN = re.compile(r"__INCOMPLETE_CHUNKS_(\d+)\.mp3$")

# Initialize the Resemble API client
#if RESEMBLEAI_API_KEY:
 #   Resemble.api_key(RESEMBLEAI_API_KEY)
#else:
 #   print("🛑 Warning: RESEMBLEAI_API_KEY environment variable not set. API calls will fail.")

def clean_text_chunk(text):
    """
    Cleans up a chunk of text and returns cleaned text string
    """
    # 1. Remove ALL line breaks and strip leading/trailing whitespace from the chunk
    current_chunk_clean = text.replace('\n', ' ') #.strip()
    # 2. Use a single regex to remove ANY surrounding whitespace from the <break> tags
    # We use a capture group (\1) to replace the tag + surrounding whitespace (\s*) with just the clean tag.
    current_chunk4 = re.sub(r'\s*(<break\s+time=".*?"/>)\s*', r'\1', current_chunk_clean)
    # 3. remove double quotation marks "
    # first isolate SSML time markers
    current_chunk5 = current_chunk4.replace('"0.3s"', '*0.3s*')
    current_chunk6 = current_chunk5.replace('"0.5s"', '*0.5s*')
    current_chunk61 = current_chunk6.replace('"0.9s"', '*0.9s*')
    current_chunk7 = current_chunk61.replace('"1s"', '*1s*')
    current_chunk8 = current_chunk7.replace('"2s"', '*2s*')
    # remove quotation marks
    current_chunk9 = current_chunk8.replace('"', '')
    # restore SSML time markers
    current_chunk10 = current_chunk9.replace('*0.3s*', '"0.3s"')
    current_chunk11 = current_chunk10.replace('*0.5s*', '"0.5s"')
    current_chunk111 = current_chunk11.replace('*0.9s*', '"0.9s"')
    current_chunk12 = current_chunk111.replace('*1s*', '"1s"')
    current_chunk13 = current_chunk12.replace('*2s*', '"2s"')
    # 4. replace white spaces after full stops with spaces, to try and eliminate hidden chars
    current_chunk14 = re.sub(r'\.\s*([A-Z])', r'. \1', current_chunk13)
    # 5. same for commas
    current_chunk15 = re.sub(r',\s*([A-Z][a-z])', r', \1', current_chunk14)
    # 6. same for colons
    current_chunk16 = re.sub(r':\s*([A-Z][a-z])', r': \1', current_chunk15)
    sanitized_text = sanitize_text(current_chunk16)
    return sanitized_text


def find_ssml_break_tag_start(text: str, index: int) -> int:
    """
    Looks backward from a given index to find the start of an SSML <break tag.
    Returns the index of '<' if found, otherwise returns -1.
    """
    # Regex to find the start of a SSML break tag: <break ...>
    # We look for '<' followed by 'break' and then the current character position.

    # We only need to search in the segment leading up to the index.
    segment = text[:index]

    # Simple check for the starting '<' of any tag
    open_tag_index = segment.rfind('<')

    if open_tag_index == -1:
        return -1

    # Now check if this tag is a break tag (e.g., <break time="0.5s"/>)
    # We'll use a lenient check that looks for `<` followed by 'break' within a reasonable distance.
    # Note: A simple string check is often sufficient here.
    if segment[open_tag_index:].lower().strip().startswith('<break'):
        # Check if the tag is still 'open' (i.e., not followed by '>')
        close_tag_index = segment[open_tag_index:].find('>')

        # If the split point is before the closing '>', we are inside the tag.
        if close_tag_index == -1:
            return open_tag_index

    return -1


def split_text_at_sentence_ends(text: str, max_chars: int = MAX_CHARS_PER_CALL) -> list[str]:
    """
        Splits a large block of text into chunks, ensuring:
        1. No chunk exceeds the max_chars limit.
        2. Splits occur only at sentence-ending punctuation (., ?, !), unless a
           single sentence is too long.
        3. Oversized sentences are split at the last space before max_chars
           to prevent mid-word splitting.
        """
    if not text:
        return []

    # Temporarily remove decimal points (full stops) between numbers so they are not treated as sentence delimiters
    text = re.sub(r'([0-9]).([0-9])', r'\1#\2', text)
    # 1. Split text into sentences (including the delimiter)
    sentence_delimiters = r'([.?!])' # r'([.?!])\s+' # No space needed after full stop now.
    # re.split returns the captured delimiters, e.g., ['Sentence 1', '.', 'Sentence 2', '!']
    sentences = [piece.strip() for piece in re.split(sentence_delimiters, text) if piece.strip()]

    chunks = []
    current_chunk = ""

    # Since we capture the delimiter, we process the list in pairs (sentence + delimiter)
    for i in range(0, len(sentences), 2):
        sentence_text = sentences[i]
        delimiter = sentences[i + 1] if i + 1 < len(sentences) else ""
        # Reconstruct the full sentence with its delimiter and a trailing space
        ext_sentence = f"{sentence_text}{delimiter} " if delimiter else sentence_text
        # Restore decimal points between numbers, i.e. within break tags like <break time="0.5s"/>
        ext_sentence = ext_sentence.replace('#', '.')
        # print("****" + ext_sentence + "****") # Debug

        # 2. Check if the current chunk can hold the next whole sentence
        if len(current_chunk) + len(ext_sentence) > max_chars and current_chunk:
            # Current chunk is full -> finalize it
            current_chunk_clean = clean_text_chunk(current_chunk)
            chunks.append(current_chunk_clean.strip())
            current_chunk = ""

        # 3. Handle a sentence that is individually too long
        if len(ext_sentence) > max_chars:
            print(
                f"⚠️ Warning: Sentence too long ({len(ext_sentence)} chars). Splitting mid-sentence to prevent mid-word break.")

            # --- WORD-SAFE SPLITTING LOGIC ---
            # Avoids spltting mid-word
            temp_sentence = ext_sentence
            while temp_sentence:
                # The maximum length we can consider for the next chunk
                max_split_len = min(len(temp_sentence), max_chars)
                chunk_to_examine = temp_sentence[:max_split_len]

                # --- NEW SSML GUARDRAIL LOGIC ---

                # Check for word boundary first (last space before max_split_len)
                split_point_word_safe = chunk_to_examine.rfind(' ')

                # Determine the initial best split point (word-safe, or max_split_len)
                if split_point_word_safe > 0 and len(temp_sentence) > max_chars:
                    initial_split_len = split_point_word_safe
                else:
                    initial_split_len = max_split_len

                # Check if the calculated split point (word-safe or max_chars) falls inside an SSML tag
                ssml_tag_start = find_ssml_break_tag_start(temp_sentence, initial_split_len)

                if ssml_tag_start != -1:
                    # We are inside a tag. Move the split point *before* the tag.
                    print(
                        f"    Moving split point from {initial_split_len} to {ssml_tag_start} to avoid splitting SSML tag.")
                    split_len = ssml_tag_start

                    # Safety check: ensure we didn't move the split to 0, which would create empty chunks
                    if split_len == 0:
                        # If the tag starts at the very beginning, we must reluctantly split *after* the tag
                        # to ensure progress, or risk splitting the tag if it's longer than max_chars.
                        # For simplicity, if split_len is 0, we force the split to occur at max_split_len
                        # and rely on the TTS engine being robust, or assume the user must fix the SSML tag.
                        split_len = max_split_len
                        print("    Tag starts at beginning, forcing split at max_chars boundary.")
                else:
                    # No SSML conflict, use the initial best split point
                    split_len = initial_split_len

                # --- END OF NEW LOGIC ---

                # Take the chunk, strip leading/trailing whitespace (the split point space is removed here)
                chunk = temp_sentence[:split_len].strip()
                chunks.append(clean_text_chunk(chunk))

                # Update the remainder of the sentence, removing any leading space from the split
                temp_sentence = temp_sentence[split_len:].lstrip()

            current_chunk = ""  # Ensure current_chunk is cleared after processing the oversized sentence

        # 4. Sentence fits, add it to the current chunk
        else:
            current_chunk += ext_sentence

    # 5. Add any remaining content in the current_chunk
    if current_chunk:
        current_chunk_clean = clean_text_chunk(current_chunk)
        chunks.append(current_chunk_clean.strip())

    return chunks

def do_backoff(attempt): # helper to wrap up this repeated code used in call_resemble_with_retry
    backoff_time = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
    time.sleep(backoff_time)
    attempt += 1
    return attempt

def call_resemble_with_retry(project_uuid, voice_uuid, chunk, chunk_index, llm_attempt, title, attempt=1, output_format: str = "mp3",
    sample_rate: int = 44100, retries: int = MAX_RETRIES, delay: int = INITIAL_BACKOFF_SECONDS):
# OLD: def call_resemble_with_retry(project_uuid, voice_uuid, chunk, title, attempt=1):
    """
    Submits a text chunk to the Resemble.ai synchronous TTS API via HTTPS request.

    Args:

        project_uuid: The UUID of the project.
        voice_uuid: The UUID of the voice to use.
        chunk: The text or SSML to synthesize.
        chunk_index: index of the chunk in the chunks list
        llm_attempt: how many attempts made at LLM rewrite
        title: The title for the generated clip.
        attempt: count of how many TTS API attempts made
        output_format: The desired audio output format (e.g., 'mp3', 'wav').
        sample_rate: The desired audio sample rate (e.g., 44100).
        retries: Number of retry attempts.
        delay: Delay in seconds between retries.

    Returns:
        A dictionary containing the JSON response from the API (which includes the base64 audio content).
    """

    # url = f"https://api.resemble.ai/api/v2/projects/{project_uuid}/clips/sync"
    url = f"https://f.cluster.resemble.ai/synthesize"
    # Use a try/finally block to ensure the API key is retrieved, or use the global one
    global RESEMBLEAI_API_KEY
    if not RESEMBLEAI_API_KEY:
        RESEMBLEAI_API_KEY = os.getenv("RESEMBLEAI_API_KEY")

    headers = {
        "Authorization": f"Bearer {RESEMBLEAI_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    # Construct the JSON payload for the synchronous API call
    if not PRESET_UUID:  # usual case no Preset
        payload = {
            "voice_uuid": voice_uuid,
            "project_uuid": PROJECT_UUID,  # if using url f"https://f.cluster.resemble.ai/synthesize"
            "title": title,
            "data": chunk,
            # "body": BODY,  # if using url f"https://app.resemble.ai/api/v2/projects/{PROJECT_UUID}/clips/"
            "output_format": 'mp3',
            "sample_rate": 32000,
        }
    else: # there is a Preset so use it
        payload = {
            "voice_uuid": voice_uuid,
            "project_uuid": PROJECT_UUID,  # if using url f"https://f.cluster.resemble.ai/synthesize"
            "title": title,
            "data": chunk,
            # "body": BODY,  # if using url f"https://app.resemble.ai/api/v2/projects/{PROJECT_UUID}/clips/"
            "output_format": 'mp3',
            "sample_rate": 32000,
            "voice_settings_preset_uuid": PRESET_UUID
        }
    chunk_count = chunk_index + 1
    while attempt <= MAX_RETRIES:
        try:
            # Make the synchronous POST request
            response = requests.post(url, headers=headers, json=payload, timeout=90)
            response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

            # The synchronous API returns the audio content directly in the response JSON
            response_json = response.json()

            # updated to trigger retry in case of non-error response but error within JSON payload:
            if not response_json.get('success'): # failed, enter retry loop
                if attempt <= MAX_RETRIES: # retry loop
                    print(f"Chunk {chunk_count} try #{attempt} failed")
                    print(response_json.get("error"))  # DEBUG
                  #  if attempt == (MAX_RETRIES-1): # final attempt. THIS IS HANDLED IN THE PROCESS CHUNK PARALLEL FUNCTION
                   #     if llm_attempt > 0: # LLM already attempted
                    #        print(f"Removing <break> tags from LLM response for last try")
                     #       chunk = re.sub(r'<break\s*[^>]*?/>', '', chunk, flags=re.IGNORECASE)
                    attempt = do_backoff(attempt)
                else:  # failed after max retries
                    return response_json
            else: # success
                return response_json

        except requests.exceptions.ConnectionError:
            print(f"Chunk {chunk_count} try #{attempt} failed: Connection error.")
            if attempt <= MAX_RETRIES:
                attempt = do_backoff(attempt)
            else:
                raise
        except requests.exceptions.Timeout:
            print(f"Chunk {chunk_count} try #{attempt} failed: Request timed out.")
            if attempt <= MAX_RETRIES:
                attempt = do_backoff(attempt)
            else:
                raise

        except requests.exceptions.RequestException as e:
            # Catch network errors, bad status codes, etc.
            print(f"Chunk {chunk_count} try #{attempt}: Network or HTTP Error. {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_details = e.response.json()
                    print(f"API Error Details: {error_details}")
                except requests.exceptions.JSONDecodeError:
                    print(f"API Error Response Text: {e.response.text}")
            if attempt <= MAX_RETRIES:
                attempt = do_backoff(attempt)
            else:
                raise

        except Exception as e:
            print(f"Chunk {chunk_count} try #{attempt} failed: {e}")
            if attempt <= MAX_RETRIES:
                attempt = do_backoff(attempt)
            else:
                raise

    return None

def handle_audio(response_json, chunk_number):
# OLD: def fetch_audio_url_with_retry(audio_url, chunk_number, max_retries=MAX_RETRIES):
    """
    Helper function to decode the returned audio content in the HTTP response.
    """
    # --- START: BASE64 DECODING LOGIC ---
    audio_content_b64 = response_json.get("audio_content")
    if not audio_content_b64:
        raise Exception(f"Resemble API response is missing 'audio_content' for chunk {chunk_number}.")
    # 1. Decode the base64 string into raw audio bytes
    audio_bytes = base64.b64decode(audio_content_b64)
    # 2. Wrap the raw bytes in an in-memory file object (io.BytesIO)
    # This makes the raw data streamable and readable by pydub/AudioSegment.
    audio_stream = io.BytesIO(audio_bytes)
    # Read all raw bytes from the stream
    raw_audio_bytes = audio_stream.read()
    # print(f"Audio processed for chunk {chunk_number}.") # Commented to reduce verbosity
    return raw_audio_bytes
    #return audio_response

# New function to submit error chunks to Gemini to re-write

def rewrite_chunk_for_tts(failed_chunk: str, chunk_index: int) -> tuple[Unset | None | Any, str] | None:
    """
    Sends a failed chunk to the LLM to be rewritten for TTS compatibility.
    """
    if not OPENROUTER_API_KEY:
        print("🛑 Error: OPENROUTER_API_KEY environment variable not set. Cannot rewrite chunk.")
        return None
    user_prompt = f"Failed Text Chunk (Chunk {chunk_index + 1}):\n\n---\n\n{failed_chunk}"

    client = OpenRouter(api_key=os.getenv("OPENROUTER_API_KEY"))
    try:
        response = client.chat.send(
            # model="openai/gpt-4o",  # Specify the model you want to use
            messages=[
                {"role": "system",
                 "content": REWRITE_SYSTEM_PROMPT
                 },
                {"role": "user",
                 "content": user_prompt
                 }
            ],
            stream=False,  # Set to True for streaming responses
        )
        #print(response.choices[0].message.content)
        #print(response.model)
        return response.choices[0].message.content, response.model
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# --- PARALLEL PROCESSING HELPER FUNCTION ---

# script_to_audio_resembleai.py (Modified function)

def process_chunk_parallel(filename_only: str, chunk: str, true_chunk_index: int) -> tuple[int, AudioSegment | None]:
    """
    Handles the API call and audio fetching for a single chunk.
    Includes an LLM rewrite fallback if the TTS API fails after max retries.

    Returns: A tuple (true_chunk_index, AudioSegment or None)
    """
    # ... (MAX_LLM_REWRITES, rewrite_chunk_for_tts, call_resemble_with_retry, etc. defined above) ...

    current_chunk_text = chunk
    llm_rewrite_attempt = 0
    llm_rewrite_fail_flag = False

    # Loop indefinitely until success or final failure return
    while True:
        try:
            title = f"{filename_only}_chunk_{true_chunk_index + 1}"

            # 1. API Call (with retry) - Uses the current version of current_chunk_text
            if not llm_rewrite_fail_flag: # if LLM call already failed, we want to skip TTS call and go direct to LLM again
                responsejson = call_resemble_with_retry(PROJECT_UUID, VOICE_UUID, current_chunk_text, true_chunk_index,
                                                llm_rewrite_attempt, title=title)

            # --- SUCCESS CHECK (TTS succeeded) ---
            if responsejson and responsejson.get('success'):

                # The rest of your success path (Audio Fetch/Return Success)
                # ...
                # clip_item = responsejson.get('item', {})
                # audio_url = clip_item.get('audio_src')

                #if not audio_url:
                 #   print(f"🛑 Error: Audio URL missing for chunk {true_chunk_index + 1}.")
                  #  return true_chunk_index, None

                # 2. Audio Fetch (with retry)
                # Assuming fetch_audio_url_with_retry and AudioSegment are defined elsewhere
                #audio_response = fetch_audio_url_with_retry(audio_url, true_chunk_index + 1)
                audio_response = handle_audio(responsejson, true_chunk_index + 1)

                if audio_response:
                    # Assuming AudioSegment is defined elsewhere
                    audio_segment = AudioSegment.from_file(io.BytesIO(audio_response), format="mp3")
                    print(
                        f"✅ Audio Chunk {true_chunk_index + 1} processed successfully (LLM Rewrite used: {llm_rewrite_attempt > 0}).")
                    return true_chunk_index, audio_segment
                else:
                    print(f"🛑 Chunk {true_chunk_index + 1} Error: Failed to fetch audio.")
                    # If audio fetch fails, it's considered a final error for this chunk
                    return true_chunk_index, None
                    # TODO: enter retry loop in this case

            # --- FAILURE PATH (TTS failed or skipped) ---

            # If we are here, TTS failed or was skipped, and we need to start/increment the LLM attempt counter
            llm_rewrite_attempt += 1

            # 1. Check if we should perform an LLM rewrite
            if llm_rewrite_attempt <= MAX_LLM_REWRITES:
                # --- INTERVENTION: LLM REWRITE ---

                if llm_rewrite_attempt == 1:
                    print(f"🔄 Chunk {true_chunk_index + 1} TTS tries failed. Submitting to LLM for rewrite attempt {llm_rewrite_attempt} of {MAX_LLM_REWRITES}")
                else: print(f"🔄 Chunk {true_chunk_index + 1} LLM rewrite attempt {llm_rewrite_attempt} of {MAX_LLM_REWRITES}")

                rewritten_chunk, rewrite_llm = rewrite_chunk_for_tts(current_chunk_text, true_chunk_index)

                if rewritten_chunk: # LLM Rewrite success
                    if rewrite_llm is None: rewrite_llm = 'NA'
                    print(f"🔄 Chunk {true_chunk_index + 1} LLM rewrite attempt {llm_rewrite_attempt} successful with model {rewrite_llm}.")
                    # Clean up rewritten chunk then update chunk text and continue for a new TTS try.
                    llm_rewrite_fail_flag = False # clear this so we can go to TTS attempt again above
                    current_chunk_text = clean_text_chunk(rewritten_chunk)
                    continue  # Go to the next TTS attempt with the rewritten text

                else: # LLM rewrite failed/returned empty. Loop back to try again.
                    print(f"🛑 Chunk {true_chunk_index + 1} LLM rewrite attempt {llm_rewrite_attempt} failed or returned empty.")
                    llm_rewrite_fail_flag = True  # ensure we skip the TTS call above
                    continue # Go to top of the loop so we can do LLM attempt again
                    # llm_rewrite_attempt = llm_rewrite_attempt+1
            # 2. FINAL CLEANUP ATTEMPT (Executed ONLY if current attempt failed AND this was the last possible LLM rewrite)
            if llm_rewrite_attempt == MAX_LLM_REWRITES + 1:
                # This block runs exactly once after the final LLM rewrite attempt fails.
                print(f"🛑 Chunk {true_chunk_index + 1} LLM rewrite attempts all failed or returned empty.")
                print(f"    Chunk {true_chunk_index + 1} removing <break> tags for last try")
                # As last resort remove <break> tags from the chunk text
                current_chunk_text = re.sub(r'<break\s*[^>]*?/>', '', current_chunk_text, flags=re.IGNORECASE)
                current_chunk_text = current_chunk_text.strip()
                llm_rewrite_fail_flag = False  # clear this so we can go to TTS attempt again above
                continue  # Restart loop for one final TTS attempt with cleaned text
            # 3. Check for absolute max attempts (MAX_LLM_REWRITES attempts + 1 final cleanup try)
            if llm_rewrite_attempt > MAX_LLM_REWRITES + 1:
                error_details = responsejson.get('error','Unknown API Error') if responsejson else 'Unknown/Connection Error'
                print(
                    f"🛑 Chunk {true_chunk_index + 1} Final Error: TTS API call failed after max retries/rewrites: {error_details}")
                print(f"**** Failed chunk text: {current_chunk_text} ****")
                return true_chunk_index, None

        except Exception as e:
            # Catches unexpected exceptions outside the TTS/Fetch process
            print(f"🛑 Chunk {true_chunk_index + 1} Fatal Error: Unrecoverable error in processing: {e}")
            return true_chunk_index, None


    # Should be unreachable, but good practice
    return true_chunk_index, None


def process_single_file(input_filepath: str, output_filepath: str, processed_script_filepath: str,
                        start_chunk_index: int, existing_audio: AudioSegment = None) -> bool:
    """
    Reads a single text file, calls the Resemble.AI TTS API in controlled batches, and saves the audio.
    """
    filename_only = os.path.basename(input_filepath)
    is_resume_job = existing_audio is not None

    print(f"\nProcessing file: {filename_only} (Mode: {'Resume' if is_resume_job else 'New'})")

    if not RESEMBLEAI_API_KEY or PROJECT_UUID == "YOUR_RESEMBLE_PROJECT_UUID" or VOICE_UUID == "YOUR_RESEMBLE_VOICE_UUID":
        print("🛑 Error: Please set RESEMBLEAI_API_KEY, PROJECT_UUID, and VOICE_UUID variables/env var.")
        return False

    # --- BLOCK 1: Read the file ---
    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            text_to_speak = f.read()

        if not text_to_speak.strip():
            print(f"🛑 Error: The file '{input_filepath}' is empty. Skipping.")
            return False

    except Exception as e:
        print(f"🛑 An error occurred while reading '{input_filepath}': {e}. Skipping.")
        return False

    # --- BLOCK 2: Process the text ---
    try:
        # 1. Split the text into logical chunks
        text_chunks = split_text_at_sentence_ends(text_to_speak, MAX_CHARS_PER_CALL)
        total_chunks = len(text_chunks)
        print(f"Total input characters: {len(text_to_speak)}")
        # print(text_chunks[0]) # DEBUG
        print(f"Text split into {total_chunks} chunk(s) for submission.")
        # DEBUG print all chunks:
        """
        for i in range(0,(len(text_chunks))):
            print("Chunk " + str(i) + ": ")
            print(text_chunks[i])  # DEBUG
            # print('\n')
        sys.exit()  # DEBUG
        """

        if is_resume_job and start_chunk_index >= total_chunks:
            print(f"✅ File was already complete (all {total_chunks} chunks processed). Skipping API calls.")
            return True

        if is_resume_job:
            print(f"▶️ Resuming from chunk index {start_chunk_index}.")

        # Initialize lists and maps
        # audio_chunks holds the final, contiguous, successful audio segments
        audio_chunks = [existing_audio] if existing_audio else []
        # chunk_results stores all parallel results, successful or failed, keyed by index
        chunk_results = {}

        # current_chunk_index tracks the first chunk *to be processed* (and the last contiguous successful chunk + 1)
        current_chunk_index = start_chunk_index
        failure_detected = False

        # Use a single executor for the entire file processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS) as executor:

            # --- Main Processing Loop ---
            while current_chunk_index < total_chunks and not failure_detected:

                # --- A. SEQUENTIAL START PHASE ---
                # Only runs for chunks < SEQUENTIAL_START_CHUNKS, OR if currently processing a failed chunk after a resume
                if current_chunk_index < SEQUENTIAL_START_CHUNKS:

                    print(f"➡️ Sequential processing for chunk {current_chunk_index + 1}/{total_chunks}...")

                    # 1. Launch a single sequential task and wait for the result immediately
                    future = executor.submit(
                        process_chunk_parallel,
                        filename_only,
                        text_chunks[current_chunk_index],
                        current_chunk_index
                    )

                    result_index, audio_segment = future.result()

                    if audio_segment is not None:
                        # Success: Append directly to audio_chunks and move index forward
                        audio_chunks.append(audio_segment)
                        current_chunk_index += 1
                    else:
                        # Immediate failure, suspend all processing
                        print(f"🛑 Chunk {result_index + 1} failed during sequential start. Halting.")
                        failure_detected = True

                # --- B. PARALLEL LOOK-AHEAD PHASE (The critical section for the fix) ---
                else:
                    look_ahead_start = current_chunk_index
                    look_ahead_end = min(total_chunks, current_chunk_index + PARALLEL_LOOK_AHEAD)

                    if look_ahead_start >= look_ahead_end:
                        break

                    print(f"\n🚀 Submitting parallel batch from chunk {look_ahead_start + 1} to {look_ahead_end}...")

                    # 1. Submit the batch of tasks and map futures to index
                    future_to_index = {}
                    for index in range(look_ahead_start, look_ahead_end):
                        future = executor.submit(
                            process_chunk_parallel,
                            filename_only,
                            text_chunks[index],
                            index
                        )
                        future_to_index[future] = index
                        time.sleep(1) # delay between each chunk submission

                    # 2. Wait for and collect results for this batch (unordered)
                    for future in concurrent.futures.as_completed(future_to_index):
                        result_index = future_to_index[future]

                        try:
                            # We only care about the audio_segment for the result storage
                            _, audio_segment = future.result()
                            chunk_results[result_index] = audio_segment
                        except Exception as exc:
                            print(f'Chunk {result_index + 1} generated an unhandled exception: {exc}')
                            chunk_results[result_index] = None

                    # 3. Check contiguous success and advance current_chunk_index
                    # Use a while loop to keep advancing the index as long as results are successful
                    # Start checking from the current_chunk_index (the next required chunk)

                    while current_chunk_index < total_chunks:

                        # Only check results that were submitted in the last batch
                        if current_chunk_index >= look_ahead_end:
                            break  # No more results from this batch to check

                        audio_segment = chunk_results.get(current_chunk_index)

                        if audio_segment is not None:
                            # Contiguous success: Add to final list and move the window forward
                            audio_chunks.append(audio_segment)
                            current_chunk_index += 1
                        else:
                            # Failure on the next required chunk: suspend immediately
                            print(f"🛑 Chunk {current_chunk_index + 1} failed. Suspending subsequent chunk processing.")
                            failure_detected = True
                            break

                    if failure_detected:
                        # Cancel any remaining pending futures in the current batch
                        for future in future_to_index.keys():
                            if not future.done():
                                future.cancel()
                        break  # Exit the main processing loop

        # --- BLOCK 3: Final Save Decision ---

        # The total_chunks_processed_in_sequence is simply the final value of current_chunk_index
        total_chunks_processed_in_sequence = current_chunk_index

        # Final success is ONLY true if the number of chunks processed in sequence
        # is equal to the total number of chunks.
        final_success = (total_chunks_processed_in_sequence == total_chunks)

        if final_success:
            print(f"\nConcatenating {total_chunks} audio chunk(s)...")
            final_audio = sum(audio_chunks)

            os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
            final_audio.export(output_filepath, format="mp3")
            print(f"✅ Success! All chunks were concatenated and saved to: {output_filepath}")
            # Move the script file to the processed scripts directory, to avoid future accidental re-processing
            script_filename = filename_only
            print(f"Script filename: {script_filename}")
            print(f" Moving script file {script_filename} to {PROCESSED_SCRIPTS_DIR}")
            try:
                # os.rename(input_filepath, processed_script_filepath)  # old code didn't work
                shutil.move(os.path.join(QUEUED_SCRIPTS_DIR, script_filename),PROCESSED_SCRIPTS_DIR, copy_function=shutil.copy2)
            except OSError as e:
                print(f"Error moving file {script_filename} to {PROCESSED_SCRIPTS_DIR}: {e}")
            # Copy audio file to the podcast queued scripts dir
            try:
                # Copy the file. shutil.copy2() preserves metadata like creation and modification times
                shutil.copy2(output_filepath, PODCAST_QUEUE_DIR)
                print(f"File '{filename_only}' copied successfully to '{PODCAST_QUEUE_DIR}'")
            except FileNotFoundError:
                print(f"Error: Source file '{filename_only}' not found.")
            except Exception as e:
                print(f"Error copying file {filename_only} to '{PODCAST_QUEUE_DIR}': {e}")
            return True  # Indicate full success

        # --- LOGIC: Save incomplete audio upon failure ---
        elif total_chunks_processed_in_sequence > 0:
            print(
                f"\nSaving incomplete audio: {total_chunks_processed_in_sequence} chunks processed sequentially before failure.")

            base_name = os.path.splitext(filename_only)[0]
            trimmed_base_name = base_name.removesuffix("_SCRIPT")
            incomplete_filename = f"{trimmed_base_name}__INCOMPLETE_CHUNKS_{total_chunks_processed_in_sequence}.mp3"
            incomplete_output_filepath = os.path.join(INCOMPLETE_AUDIO_DIR, incomplete_filename)

            # Concatenate only the sequential successful chunks (stored in audio_chunks)
            incomplete_audio = sum(audio_chunks)

            os.makedirs(os.path.dirname(incomplete_output_filepath), exist_ok=True)
            incomplete_audio.export(incomplete_output_filepath, format="mp3")

            print(f"⚠️ Partial audio saved to: {incomplete_output_filepath}")
            return False  # Indicate partial success/failure

        else:
            print("\nNo audio chunks were generated. Output file was not created.")
            return False

    except Exception as e:
        print(f"An unexpected error occurred during API or audio processing for this file: {e}")
        return False


def main():
    """Main function to iterate through all scripts, prioritizing incomplete files."""

    print("\n--- RESEMBLE.AI BATCH AUDIO GENERATION START (Controlled Parallel Mode) ---")

    # 1. Ensure output directories exist
    os.makedirs(OUTPUT_AUDIO_DIR, exist_ok=True)
    os.makedirs(INCOMPLETE_AUDIO_DIR, exist_ok=True)

    if not RESEMBLEAI_API_KEY:
        print("ERROR: RESEMBLEAI_API_KEY environment variable is not set.")
        sys.exit(1)

    # --- STAGE 1: CHECK FOR INCOMPLETE FILES AND RESUME ---
    print("\n--- STAGE 1: Checking for incomplete files to resume... ---")

    incomplete_files = [f for f in os.listdir(INCOMPLETE_AUDIO_DIR) if f.endswith(".mp3")]

    if incomplete_files:
        print(f"Found {len(incomplete_files)} incomplete file(s) for resuming.")

        for index, incomplete_filename in enumerate(incomplete_files):
            file_number = index + 1
            print("\n" + "=" * 50)
            print(f"** RESUME FILE {file_number} of {len(incomplete_files)}: {incomplete_filename} **")
            print("=" * 50)

            match = INCOMPLETE_CHUNK_PATTERN.search(incomplete_filename)
            if not match:
                print(f"Skipping '{incomplete_filename}': Could not parse chunk index.")
                continue

            # Parse start index and source filename
            start_chunk_count = int(match.group(1))
            # Reconstruct the original script name
            base_script_name = incomplete_filename.split("__INCOMPLETE_CHUNKS_")[0] + "_SCRIPT" + ".txt"
            incomplete_mp3_path = os.path.join(INCOMPLETE_AUDIO_DIR, incomplete_filename)
            source_script_path = os.path.join(QUEUED_SCRIPTS_DIR, base_script_name)
            processed_script_path = os.path.join(PROCESSED_SCRIPTS_DIR, base_script_name)

            if not os.path.exists(source_script_path):
                print(
                    f"🛑 Error: Source script '{base_script_name}' not found in '{QUEUED_SCRIPTS_DIR}'. Skipping resume.")
                continue

            try:
                print(f"Loading {start_chunk_count} existing chunks from {incomplete_filename}...")

                # Load the single incomplete audio file
                full_incomplete_audio = AudioSegment.from_mp3(incomplete_mp3_path)

                # Determine the final output path
                base_name = os.path.splitext(base_script_name)[0]
                trimmed_base_name = base_name.removesuffix("_SCRIPT")
                output_filename = f"{trimmed_base_name}.mp3"
                output_filepath = os.path.join(OUTPUT_AUDIO_DIR, output_filename)

                # Call the processing function with resume parameters
                success = process_single_file(
                    input_filepath=source_script_path,
                    output_filepath=output_filepath,
                    processed_script_filepath=processed_script_path,
                    start_chunk_index=start_chunk_count,
                    existing_audio=full_incomplete_audio
                )

                # --- CLEAN UP ON SUCCESS ---
                if success:
                    print(f"✅ Resume successful. Deleting incomplete file: {incomplete_filename}")
                    os.remove(incomplete_mp3_path)
                    # Move the script file to the processed scripts directory, to avoid future accidental re-processing
                    print(f" Moving script file {base_script_name} to {processed_script_path}")
                    try:
                        os.rename(source_script_path, processed_script_path)
                    except OSError as e:
                        print(f"Error moving file {base_script_name}: {e}")

            except Exception as e:
                print(f"❌ Failed to load or resume processing for {incomplete_filename}: {e}")
                continue

    else:
        print("No incomplete files found. Proceeding to process new scripts.")

    # --- STAGE 2: PROCESS NEW SCRIPTS ---
    print("\n--- STAGE 2: Processing new scripts from queued_scripts directory... ---")

    if not os.path.isdir(QUEUED_SCRIPTS_DIR):
        print(f"The input directory '{QUEUED_SCRIPTS_DIR}' does not exist. Please create it and add your scripts.")
        return

    script_files = [f for f in os.listdir(QUEUED_SCRIPTS_DIR) if f.endswith(".txt")]
    total_files = len(script_files)

    if total_files == 0:
        print(f"No new .txt files found in the '{QUEUED_SCRIPTS_DIR}' directory. Exiting.")
        return

    print(f"Found {total_files} new script(s) to process.")

    # Process each new file
    found = False
    for index, filename in enumerate(script_files):
        file_number = index + 1
        # code to check if there is an incomplete file for this script, then skip
        for index, incomplete_filename in enumerate(incomplete_files):
            # check match of filename and incomplete_filename modded to be script
            incomplete_script_name = incomplete_filename.split("__INCOMPLETE_CHUNKS_")[0] + "_SCRIPT" + ".txt"
            if filename == incomplete_script_name:
                found = True
                break  # Exits the inner loop
        if found:
            break  # Exits the outer loop
        print("\n" + "=" * 50)
        print(f"** NEW FILE {file_number} of {total_files} **")
        print("=" * 50)

        # 3a. Dynamically set file paths
        input_filepath = os.path.join(QUEUED_SCRIPTS_DIR, filename)
        # Construct the output filename: replace .txt with __AUDIO.mp3
        base_name = os.path.splitext(filename)[0]
        trimmed_base_name = base_name.removesuffix("_SCRIPT")
        output_filename = f"{trimmed_base_name}.mp3"
        output_filepath = os.path.join(OUTPUT_AUDIO_DIR, output_filename)
        processed_script_filepath = os.path.join(PROCESSED_SCRIPTS_DIR, filename)

        # 3b. Skip if the output file already exists
        if os.path.exists(output_filepath):
            print(f"Skipping {filename}: Output file already exists at {output_filepath}")
            continue

        # 3c. Process the file (Not a resume job)
        process_single_file(input_filepath, output_filepath, processed_script_filepath, start_chunk_index = 0)

    print("\n--- RESEMBLE.AI BATCH AUDIO GENERATION COMPLETE ---")


if __name__ == "__main__":
    main()