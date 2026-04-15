#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Async report + script generator using Google Gemini (2.5 Flash Free Tier friendly)
with robust timeouts, progress logging, and safe error handling.

Now also reads optional CSV columns ID and Category, and names files as:
  ID_Category_Topic_Date_REPORT.txt
  ID_Category_Topic_Date_SCRIPT.txt
(or "NA" for any missing piece)

--- MODIFICATION ---
NOW: Generates a short podcast description and writes it back to the input CSV.

Install
-------
pip install google-genai google-generativeai python-dateutil pandas

Run
---
export GEMINI_API_KEY="YOUR_API_KEY"
python generate_reports_and_scripts_async.py \
  --csv ./topics.csv \
  --outdir ./out \
  --model gemini-2.5-flash \
  --script_instructions "/mnt/data/LLM Script Generation Instructions.txt" \
  --outline_schema_hint "/mnt/data/Outline JSON.json" \
  --max_concurrency 3
"""

import argparse
import asyncio
import csv
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Coroutine, List
from openrouter import OpenRouter
from typing_extensions import LiteralString
from urllib.parse import urlparse
from typing import List
import json
import base64
import requests
from extract_outline_from_report import extract_outline
import traceback
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, TemplateError, TemplateSyntaxError, StrictUndefined
import warnings
from pathlib import Path

sys.path.append(os.path.abspath('..')) # required to get path to sister directory for script imports
from scripts_utilities.utility_ssml_and_year_correction import process_document_for_ssml, replace_years_in_text
from scripts_utilities.utility_calc_sentence_lengths import analyze_sentence_length

# ===================== Files Path =====================
PODCAST_GENERATOR_DIR = os.path.join(os.getenv('PODCAST_GENERATOR_DIR'))

# ===================== Tunables (env overrides) =====================
REQ_TIMEOUT_SEC = int(os.getenv("LLM_REQ_TIMEOUT_SEC", "180"))  # each LLM request
ACQUIRE_MAX_WAIT_SEC = int(os.getenv("RATE_ACQUIRE_MAX_WAIT_SEC", "90"))  # max wait before heartbeat
SECTION_WATCHDOG_SEC = int(os.getenv("SECTION_WATCHDOG_SEC", "240"))  # one section
TOPIC_WATCHDOG_SEC = int(os.getenv("TOPIC_WATCHDOG_SEC", "3600"))  # whole topic
BACKOFF_MAX_SEC = int(os.getenv("BACKOFF_MAX_SEC", "8"))
SECTION_RETRIES_ON_FAIL = int(os.getenv("SECTION_RETRIES_ON_FAIL", "2")) # Max retries for a single section generation on timeout/failure
LLM_FILE_ACCESS_FAILURE_MSG = "LLM_FILE_READ_ERROR"
LLM_CALL_ATTEMPTS = 4 # Max retries for single LLM API call if returns error
# Word Count Margins
WORDCOUNT_FLOOR_RATIO = float(os.getenv("WORDCOUNT_FLOOR_RATIO", "0.95"))  # Minimum acceptable ratio (0.90 = -10%)
SCRIPT_WC_UNDER_MARGIN = float(os.getenv("SCRIPT_WC_UNDER_MARGIN", "0.05"))  # % under target (0.10 = 10%)
SCRIPT_WC_OVER_MARGIN = float(os.getenv("SCRIPT_WC_OVER_MARGIN", "0.12"))  # % over target (0.10 = 10%)
SCRIPT_MIN_SENTENCE_LENGTH = float(os.getenv("SCRIPT_MIN_SENTENCE_LENGTH", "15"))  # Min average length of sentences in script
SCRIPT_WC_SCALE_UP = float(os.getenv("SCRIPT_WC_SCALE_UP", "1.1"))  # Amount to increase the script to report wc ratio which is told
# to the LLM, to try and get it (Claude) to not undershoot the script wc target.
NON_STANDARD_CHAR_MAP = { # Characters in topics CSV to be cleaned up before read
    '“': '"',
    '”': '"',
    '’': "'",
    '‘': "'",
    '—': '-',  # Em dash
    '–': '-',  # En dash
    '\ufeff': '',  # Often the BOM not caught by "utf-8-sig"
}
SENTENCE_MAX_CHARS = 600 # limit to length of a single sentence, due to later TTS chunking process

# Rate limits (Free Tier – adjust if your project differs)
"""
RPM = int(os.getenv("GEMINI_LIMIT_RPM", "10"))
TPM = int(os.getenv("GEMINI_LIMIT_TPM", "250000"))
RPD = int(os.getenv("GEMINI_LIMIT_RPD", "250"))
"""

# Text inputs for prompts construction
manifest_path = os.path.join(PODCAST_GENERATOR_DIR,"/reference files/inputs_manifest.csv")  # key to all other inputs
library_dir = os.path.join(PODCAST_GENERATOR_DIR, "/reference files/inputs_library")

history_report_prose_sample_path = os.path.join(PODCAST_GENERATOR_DIR,"/reference files/JB_Bury_sample.txt")
history_script_style_sample_path = os.path.join(PODCAST_GENERATOR_DIR,"/reference files/Doug_Metzger_sample.txt")
technical_report_prose_sample_path = os.path.join(PODCAST_GENERATOR_DIR,"/reference files/Vu_Trinh_sample.txt")
technical_script_style_sample_path = os.path.join(PODCAST_GENERATOR_DIR,"/reference files/Seattle_Data_Guy_sample.txt")

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    print("Set OPENROUTER_API_KEY environment variable.")
    raise SystemExit(1)

# ===================================================================

# Timezone for filenames (AU/Perth as requested in earlier versions)
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None

# Optional: pandas preview
try:
    import pandas as pd  # noqa: F401

    HAS_PANDAS = True
except Exception:
    HAS_PANDAS = False


# ------------------------- Utility logging -------------------------

def ts() -> str:
    """Timestamp for logs."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def info(msg: str):
    print(f"[{ts()}] {msg}")


def warn(msg: str):
    sys.stderr.write(f"\033[33m [{ts()}] [WARNING] {msg} \033[0m \n")
    # print(f"[{ts()}] [WARN] {msg}", file=sys.stderr) # original


def err(msg: str):
    print(f"[{ts()}] [ERROR] {msg}", file=sys.stderr)

# ------------------------- Handling PDF References -------------------------

def get_pdf_filenames(pdf_links) -> List[List[str]]:
    """
    Takes the list of pdf URLs, extracts the filename from the end of each URL,
    and returns as a 2D list of [url, filename].

    Parameters
    ----------
    pdf_links: List[str]
        List of URLs

    Returns
    -------
    List[List[str]]
        2D list in the form [[url/path, filename], ...]
    """
    pdf_links_with_names = []

    for link in pdf_links:
        link = link.strip()
        # 1. Use urlparse to get the path (handles http/https)
        parsed = urlparse(link)
        # 2. Use Path to extract the name (handles / and \ automatically)
        # parsed.path works for URLs; link works for local paths
        raw_path = parsed.path if parsed.scheme else link
        filename = Path(raw_path).name
        pdf_links_with_names.append([link, filename])

    #print(pdf_links_with_names) # DEBuG
    return pdf_links_with_names


def encode_local_pdfs(local_pdfs) -> List:  # Base64 encode function for local URL list
    encoded_list = [] # initialise
    for i in range(len(local_pdfs)):
        with open(local_pdfs[i][0], "rb") as pdf_file:
            base64_pdf = base64.b64encode(pdf_file.read()).decode('utf-8') # encode
            data_url = f"data:application/pdf;base64,{base64_pdf}" # generate url string
            encoded_list.append([data_url, local_pdfs[i][1]]) # put url string and file name into list
            # outputfilename = local_pdfs[i][1]  # TEMP DEBUG, test decoding the encode back into pdf
            # decode = base64.b64decode(base64_pdf) # TEMP DEBUG
            #with open(outputfilename, "wb") as f:  # TEMP DEBUG
             #   f.write(decode)  # TEMP DEBUG
    return encoded_list


def construct_api_payload(     # Construct payload for Openrouter API call with/ without PDF file inclusions
        system_prompt,
        user_prompt,
        references: Optional[List[Dict[str, str]]] = None,
        file_annotations: Optional[Dict] = None,
        use_native_pdf: bool = False  # NEW PARAMETER
) -> list[dict[str, str | Any] | dict[str, str | list[dict[str, str | Any]]]]:

    user_content_list = []
    user_text = user_prompt # default value
    """user_content_list = [
        {
            "type": "text",
            "text": user_prompt
        }
    ]"""
    if references:
        # print("construct_api_payload references:" + str(references)) # DEBUG
        #TODO: add web pages
        public_pdfs = [item['value'] for item in references if item['type']=='public pdf'] # list comprehension get only for items of the right type in references
        local_pdfs  = [item['value'] for item in references if item['type']=='local pdf']  # list comprehension get only for items of the right type in references
        # print("local_pdfs: " + str(local_pdfs)) # DEBUG
        if len(public_pdfs) > 0: #TODO: update with native processing option as per local
            public_pdfs_filenames = get_pdf_filenames(public_pdfs)  # extract filenames from public pdfs
            filenames = []  # initialise
            for data_path, filename in public_pdfs_filenames:
                filenames.append(filename)
                user_content_list.append({
                    "type": "file",
                    "file": {
                        "filename": f"{filename}",
                        #"file_data": f"{public_pdfs[i][0]}"
                        "file_data": f"PDF FILENAME"
                    }
                }
                )
            user_text = (
                f"I have attached the following file(s): {filenames}. Please use the file content to answer: {user_prompt}."
                f"If the file content cannot be accessed, strictly return only {LLM_FILE_ACCESS_FAILURE_MSG}")

        if len(local_pdfs) > 0:
            local_pdfs_filenames = get_pdf_filenames(local_pdfs)
            local_encoded_pdfs = encode_local_pdfs(local_pdfs_filenames)  # extract filenames from local pdfs and encode base64 link
            # print("*** Local PDF Filenames: " + str(get_pdf_filenames(local_pdfs))) # DEBUG
            # print("*** length local_encoded_pdfs: " + str(len(local_encoded_pdfs)))  # DEBUG
            filenames = [] # initialise
            for data_path, filename in local_encoded_pdfs:
                print("local_pdfs filename: " + filename)  # DEBUG
                filenames.append(filename)
                if use_native_pdf:
                    print(str(data_path)[0:50])
                    # NATIVE MODE: Standard multimodal block
                    # Note: We ensure the base64 string is 'clean'
                    # print(filename) # DEBUG
                    # print(str(data_path)[0:100]) # DEBUG
                    # IMPORTANT: Extract ONLY the base64 part, removing the prefix
                    raw_base64 = data_path.split(",")[1] if "," in data_path else data_path
                    user_content_list.append({
                        "type": "image_url", #""file",
                        "image_url": { #"file": {
                            "name": filename,
                            "mime_type": "application/pdf",
                            "data": data_path.replace("\n", "").strip() #raw_base64.replace("\n", "").strip()
                        }
                    })
                else:
                    # PLUGIN MODE: Current OpenRouter file-parser structure
                    user_content_list.append({
                        "type": "file",
                        "file": {
                            "filename": filename,
                            "file_data": data_path
                        }
                    })
            user_text = (
                f"I have attached the following file(s): {str(filenames)}. Please use the file content to answer: {user_prompt}."
                f"If the file content cannot be accessed, strictly return only {LLM_FILE_ACCESS_FAILURE_MSG}")


    # CRITICAL: Append the text prompt AFTER the files for better model attention
    user_content_list.append({
        "type": "text",
        "text": user_text
    })

    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": user_content_list
        }
    ]
    print("messages length:" + str(len(str(messages))))  # Debug
    # print("messages:" + str(messages)[0:300])  # Debug
    #file_annotations =  "DEBUG FILE ANNOTATIONS PLACEHOLDER"  # DEBUG
    if file_annotations:
        messages.append({
                "role": "assistant",
                "content": "The document contains information about...",
                "annotations": file_annotations
                }
                )
    #print(messages) # DEBUG
    return messages


# ------------------------- OpenRouter Client (current APIs) -------------------------

class OpenRouterClient:
    """
    Supports:
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None
        self._setup()

    def _setup(self):  # not used as client created at top of script for universal usage
       self._client = OpenRouter(api_key=self.api_key)

    async def generate(
            self,
            api_key: str,
            system_prompt: Optional[str],
            user_prompt: str,
            temperature: Optional[float] = 1.0,
            references: Optional[List[Dict[str, str]]] = None,
            file_annotations: Optional[Dict] = None,
            use_native_pdf: Optional[bool] = False # NEW PARAMETER
    ) -> tuple[None, None, None, None] | tuple[None, None, None, Any] | tuple[Any, Any, dict | None | Any, None]:
        """
        Returns text content using the appropriate SDK call.
        """
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "anthropic/claude-sonnet-4", # "google/gemini-2.5-flash-lite", # optional. This has been set in Openrouter settings.
            "messages": construct_api_payload(system_prompt, user_prompt, references, file_annotations, use_native_pdf),
            "temperature": temperature,  # default is 1. Increased to promote slightly more creativity and length.
            "max_tokens": 6000 # TODO: increase for single-request script generation, or change into a variable
            #, "plugins": [] # see below
            # OK to keep this even when no pdfs are included
        }
        # PLUGIN LOGIC: If native is False, we use the explicit file-parser plugin.
        # If native is True, we tell OpenRouter to use the model's native engine.
        if not use_native_pdf:
            payload["plugins"] = [{"id": "file-parser", "pdf": {"engine": "pdf-text",}}]
        #else: # Leave plugins out entirely
            # Explicitly requesting native processing (or omit to let OpenRouter decide)
         #   payload["plugins"] = [{"id": "file-parser", "pdf": {"engine": "native",}}]
        print(str(payload)[0:500])  # DEBUG
        #print(str(payload["plugins"]))  # DEBUG
        # printing payload messages content for DEBUG:
        # Assuming your payload is: payload = {"model": "...", "messages": [...]}
        content_array = payload['messages'][0]['content']
        for i, block in enumerate(content_array):
            if isinstance(block, dict):
                # It's a structured block (text or file)
                block_type = block.get('type', 'unknown')
                if block_type == 'text':
                    text_content = block.get('text', '')
                    print(f"Block {i}: [TEXT] Length={len(text_content)}")
                else:
                    print(f"Block {i}: [FILE/OTHER] Type={block_type}")
            elif isinstance(block, str):
                # It's just a plain string
                continue
                #print(f"Block {i}: [RAW STRING] Length={len(block)}")

        # Check if the base64 string actually exists in the final payload, for Debugging
        print(f"Total payload size: {len(json.dumps(payload))} bytes") # DEBUG
        # launch the actual API request
        try:
            response = requests.post(url, headers=headers, json=payload)
            response_json = response.json()

            # print(response_json) # DEBUG
            if "choices" in response_json:
                response_content = response_json['choices'][0]['message']['content']
                response_model = response_json['model']
                # print(response_content) # DEBUG
                # print(response_model) # DEBUG

                # get file annotations if we don't already have them
                if file_annotations is None: # case no previous annotations received in call
                    if response_json.get("choices") and len(response_json["choices"]) > 0:
                        if "annotations" in response_json["choices"][0]["message"]:
                            file_annotations = response_json["choices"][0]["message"]["annotations"]
                #            print(file_annotations) # DEBUG
               # print(str(response_json)[:100]) # DEBUG
                return response_content, response_model, file_annotations, None
            else:
                # This will show you the ACTUAL error message from OpenRouter
                error = json.dumps(response_json, indent=2)
                print("API Error Response:", error)
                # response_content=None
                # response_model=None
                return None, None, None, response_json

        except Exception as e:
            print(f"An error occurred: {e}")
            return None, None, None, None

client = OpenRouterClient(api_key=api_key)
# TODO: not ideal to have this here but needs to be global and needs to follow class declaration and before usage
# print("OpenRouter API key set to" + str(client.api_key)) # DEBUG

async def llm_call(
        system_prompt: Optional[str],
        user_prompt: str,
        temperature: Optional[float] = 1.0,
        references: Optional[List[Dict[str, str]]] = None,
        file_annotations: Optional[Dict] = None
) -> tuple[Any, Any, Any | None] | None:
    """LLM call with RPM/TPM gating, backoff, and a hard timeout."""
    # print("llm_call")  # debug
    key = client.api_key
    response = None
    attempts = 1
    # TODO: catch 400 errors
    while response is None and attempts <= LLM_CALL_ATTEMPTS:
        error_details = None # initialise/ reset
        if attempts > 1: print(f"LLM error OR error in generate function, retrying call {attempts} of {LLM_CALL_ATTEMPTS}.")
        try:
            response, model, annotations, error_details = await asyncio.wait_for(client.generate(key, system_prompt, user_prompt,
                                                                                  temperature, references, file_annotations),
                                                                  timeout=REQ_TIMEOUT_SEC)
        except Exception as e:
            print(f"Error in llmcall function from generate function: {e}")

        if error_details and error_details['error']['message'] == 'Invalid content':
            response = "Failed to generate due to error in API call"
            return response, "", ""

        attempts += 1
        if attempts == LLM_CALL_ATTEMPTS + 1: model, annotations = None, None
    return response, model, annotations

# ------------------------- Data Structures & Helpers -------------------------


class ModeMatrix:
    """
       Class for the Generation Mode Matrix which contains the configuration for each generation mode
       Store in memory and lookup and retrieve values of tasks from the Matrix. 
       """
   
    def __init__(self, matrix_path: str):
        self.matrix_path = Path(matrix_path)
        self.tasks = {}
        self._load_matrix()

    def _load_matrix(self):
        with open(self.matrix_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Store the whole row using task_id as the key
                self.tasks[row['mode_id']] = row

    def get_mode_tasks(self, mode_id: str, task_type: str) -> str:
        """
        Returns a single cell from the Generation Mode Matrix
        """
        mode_row = self.tasks.get(mode_id)
        if not mode_row:
            raise ValueError(f"Mode {mode_id} not found in matrix.")
        mode_task = mode_row[task_type]
        return mode_task


class InputManifest:
    """
    Class for the Input Manifest table of links to prompts text and other prompt input. Store in memory and lookup and
    retrieve values from underlying files. 
    """
    def __init__(self, manifest_path: str, library_dir: str = library_dir):
        self.manifest_path = Path(manifest_path)
        self.library_dir = Path(library_dir)
        self.tasks = {}
        self._load_manifest()
        # The Environment is key: it knows how to "include" other files from the folder
        self.env = Environment(loader=FileSystemLoader(library_dir))

    def _load_manifest(self):
        with open(self.manifest_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Store the whole row using task_id as the key
                self.tasks[row['mode_id']] = row

    def _read_file(self, filename: str) -> str:
        if not filename: return ""
        path = self.library_dir / filename
        return path.read_text(encoding='utf-8') if path.exists() else ""

    def get_mode_prompt_inputs(self, mode_id: str, input_type: str) -> str:
        """
        Returns an entry from the inputs manifest, read from the underlying file, e.g. system prompt text, user prompt text
        sample jsons, etc.
        """
        mode_row = self.tasks.get(mode_id)
        if not mode_row:
            raise ValueError(f"Mode {mode_id} not found in manifest.")
        prompt_input = self._read_file(mode_row[input_type])
        return prompt_input

    def build_prompt(self, mode_id: str, prompt_template: str, **kwargs) -> str:
        """
        Constructs an entire prompt for one mode and role. Using Jinja library, gets the row of the input_manifest
        for the mode as a dictionary, appends with any other variable names passed in the function call, and passes them
        into the specified prompt template which contains the variable fields, returns the entire prompt.
        sample jsons, etc.
          """
        mode_row = self.tasks.get(mode_id)
        # print(str(mode_row)) # DEBUG
        # We pass the filenames from the CSV into the template as variables
        # This allows {% include style_file %} to work inside the text files.
        render_data = {**mode_row, **kwargs}
        # Just load and render the top-level files defined in the input_manifest CSV
        # {"role": "user", "content": user_tmpl.render(render_data)}
        try:
            prompt_tmpl = self.env.get_template(mode_row[prompt_template])
            prompt = prompt_tmpl.render(render_data)
            return prompt
        except TemplateSyntaxError as e:
            print(f"Jinja Syntax Error: {e.message}")
            print(f"Error occurred on template line: {e.lineno}")
        except TemplateError as e:
            print(f"Jinja rendering error: {e}")
        except Exception as e:
            print(f"Unexpected error during Jinja prompt rendering: {e}")

        return ""


@dataclass
class OutlineSection:
    section_number: int
    section_title: str
    allocated_word_count: int
    chapter_mapping: Optional[List[str]] = None
    purpose: Optional [str] = None
    sub_sections: Optional[List[str]] = None
    key_technical_requirements: Optional[List[str]] = None
    non_obvious_insights: Optional[str] = None


@dataclass
class Outline:
    topic: str
    target_word_count: int
    outline_sections: List[OutlineSection]


SECTION_RETRIES = 3
SCRIPT_RETRIES = 4  # Increased from 1 to 3 for revision attempts
OUTLINE_RETRIES = 3
OUTLINE_TOLERANCE = 0.12  # ±10%


def word_count(txt: str) -> int:
    return len(re.findall(r"\b\w+\b", txt or ""))


def sanitize_filename_component(s: str) -> str:
    s = re.sub(r"[^\w\s\-.]", "", s, flags=re.UNICODE)
    # s = re.sub(r"\s+", "_", s.strip())  don't want to insert underscores anymore
    return s[:150] if len(s) > 150 else s


def timestamp_str() -> str:
    tz = ZoneInfo("Australia/Perth") if ZoneInfo else None
    now = datetime.now(tz=tz)
    return now.strftime("%Y%m%d-%H%M%S%z")


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def try_json_load(txt: str) -> Dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (txt or "").strip(), flags=re.DOTALL)
    return json.loads(cleaned)


def validate_outline_struct(o: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(o, dict):
        return False, "Outline is not a JSON object."
    for k in ["topic", "target_word_count", "outline_sections"]:
        if k not in o:
            return False, f"Missing key in outline: {k}"
    if not isinstance(o["outline_sections"], list) or not o["outline_sections"]:
        return False, "Outline.sections must be a non-empty list."
    for i, sec in enumerate(o["outline_sections"]):
        for k in ["section_number", "section_title", "allocated_word_count"]:
            if k not in sec:
                return False, f"Section {i} missing '{k}'."
    return True, "ok"

# ------------------------- Outline / Section / Script / Description Gen -------------------------

def parse_outline(data: Dict[str, Any]) -> Outline:
    ok, msg = validate_outline_struct(data)
    if not ok:
        raise ValueError(f"Invalid outline JSON: {msg}")
    sections = [
        OutlineSection(
            section_number = s['section_number'],
            section_title=s["section_title"],
            allocated_word_count=int(s["allocated_word_count"]),
            purpose=s.get("purpose"),
            chapter_mapping=s.get("chapter_mapping"),
            key_technical_requirements=s.get("key_technical_requirements"),
            non_obvious_insights = s.get("non_obvious_insights"),
            sub_sections=s.get("sub_sections"),
        )
        for s in data["outline_sections"]
    ]
    return Outline(
        topic=data["topic"],
        target_word_count=int(data["target_word_count"]),
        outline_sections= sections
    )


def outline_sum_within_tolerance(outline: Outline, target_wc: int, tol: float = OUTLINE_TOLERANCE) -> Tuple[bool, int]:

    total = sum(s.allocated_word_count for s in outline.outline_sections)
    lower = int(target_wc * (1 - tol))
    upper = int(target_wc * (1 + tol))
    return (lower <= total <= upper), total


def check_llm_file_access_error(text: str) -> bool:  # TODO: remove this now with local pdf processing ?
    """
    Checks if text (returned from LLM) contains the specified error message indicating failure to access file
    """
    # maybe change this to use LLM to evaluate the text for error message
    if LLM_FILE_ACCESS_FAILURE_MSG in text:
        return True
    elif LLM_FILE_ACCESS_FAILURE_MSG.lower() in text:
        return True
    elif LLM_FILE_ACCESS_FAILURE_MSG.lower().capitalize() in text:
        return True
    else:
        return False


def parse_chapters_from_summary(markdown_text: str) -> List[Dict[str, Any]]:
    """
    Extract chapter metadata from Book Summary markdown headings.

    Expected headings like:
      #### Chapter 0 Introduction
      #### Chapter 01 An Overview...
      #### Chapter 10 The Future...

    Returns:
      [
        {
          "raw_heading": "#### Chapter 01 An Overview...",
          "number": 1,
          "number_str": "01",
          "label": "Chapter 01",
          "title": "An Overview..."
        },
        ...
      ]
    """
    chapter_pattern = re.compile(
        r'^\s*#{1,6}\s*Chapter\s+(\d+)\b(.*)$',
        re.IGNORECASE | re.MULTILINE
    )

    chapters: List[Dict[str, Any]] = []

    for match in chapter_pattern.finditer(markdown_text):
        number_str = match.group(1)
        trailing_title = match.group(2).strip()
        number = int(number_str)

        # Preserve Chapter 0 as "Chapter 0".
        # Preserve zero-padding for non-zero chapters if present in the source.
        label = f"Chapter {number_str}" if number == 0 else f"Chapter {number_str.zfill(2)}"

        chapters.append({
            "raw_heading": match.group(0).strip(),
            "number": number,
            "number_str": number_str,
            "label": label,
            "title": trailing_title
        })

    return chapters


def build_chapter_prompt_vars_from_summary(summary_path: str) -> Dict[str, Any]:
    """
    Read the Book Summary markdown file and build chapter-related prompt variables.

    Returns keys:
      valid_chapter_ids
      chapter_numbers
      chapter_count
      chapter_count_excluding_intro
      has_chapter_zero
      chapters_structured
    """
    with open(summary_path, "r", encoding="utf-8") as f:
        markdown_text = f.read()

    chapters = parse_chapters_from_summary(markdown_text)
    if not chapters:
        raise ValueError(f"No chapter headings found in Book Summary file: {summary_path}")

    chapters_sorted = sorted(chapters, key=lambda x: x["number"])
    valid_chapter_ids = [c["label"] for c in chapters_sorted]
    chapter_numbers = [c["number"] for c in chapters_sorted]

    return {
        "valid_chapter_ids": valid_chapter_ids,
        "chapter_numbers": chapter_numbers,
        "chapter_count": len(chapters_sorted),  # compatibility with existing prompt
        "chapter_count_excluding_intro": len([n for n in chapter_numbers if n != 0]),
        "has_chapter_zero": 0 in chapter_numbers,
        "chapters_structured": chapters_sorted,
    }


async def generate_report_outline(
        # TODO: RESTRUCTURE   generate_outline just needs mode, topic, target wc, optional subtopics, optional reference list, opt use refs flag.
        # TODO: RESTRUCTURE   schema and anything else will come from manifest.  The book chapter summary will be part of references list
        # TODO: RESTRUCTURE   as an item with type local pdf.
        # TODO: remove pdf_annotations from return
        process_inputs: InputManifest,
        generation_mode: str,
        topic: str,
        report_target_wc: int,
        subtopics_str: Optional[str] = None,
        guidelines: Optional[str] = None,
        reference_material: Optional[List[Dict[str, str]]] = None,
        flag_use_refs_only: Optional[bool] = None
) -> tuple[Outline | None, object | None]:
    """
    Generates a structured outline for the nominated topic. Requests outline for topic from LLM API based on sample
    schema. Optionally includes reference material (book summary) with the API request. Checks that the
     specified word count per report section in the outline meets the total report target word count,
     regenerates the outline if word count falls short. Returns an Outline object (and pdf annotations,
     no longer required). Looks up most information for the API request from the InputManifest file, including prompts.
    Updated logic:
    - Finds the Book Summary markdown file in reference_material
    - Parses chapter headings from the summary itself
    - Passes exact valid chapter IDs into the prompt
    - Uses parsed summary chapters for chapter_count instead of counting files
    """
    info(f"Requesting outline for topic: {topic}")

    summary_keywords = ["book summary", "book_summary"]
    summary_file_entry: Optional[Dict[str, str]] = None
    outline_reference_material = reference_material

    # Identify the Book Summary file and keep only that file for outline generation,
    # preserving the existing behaviour of passing the summary only.
    if reference_material:
        for file_entry in reference_material:
            value = str(file_entry.get("value", "")).strip()
            if not value:
                continue

            filename = os.path.basename(value).lower()
            if any(word in filename for word in summary_keywords):
                summary_file_entry = file_entry
                outline_reference_material = [file_entry]
                break

    valid_chapter_ids: List[str] = []
    chapter_count = 0

    if summary_file_entry:
        summary_path = str(summary_file_entry["value"]).strip()

        try:
            chapter_vars = build_chapter_prompt_vars_from_summary(summary_path)
            valid_chapter_ids = chapter_vars["valid_chapter_ids"]
            chapter_count = chapter_vars["chapter_count"]

            info(
                f"Parsed chapters from summary: {valid_chapter_ids} "
                f"(count={chapter_count}, has_chapter_zero={chapter_vars['has_chapter_zero']})"
            )
        except Exception as e:
            warn(f"Failed to parse chapters from Book Summary '{summary_path}': {e}")
            valid_chapter_ids = []
            chapter_count = 0
    else:
        warn("No Book Summary file found in reference_material; chapter constraints will be weaker.")

    print("*** Outline reference material: " + str(outline_reference_material))  # DEBUG

    # Prompt variables.
    # Keep chapter_count for backward compatibility with the existing prompt.
    # Add valid_chapter_ids so the prompt can constrain chapters exactly.
    user_kwargs = {
        "report_topic": topic,
        "report_target_wc": report_target_wc,
        "reference_material": outline_reference_material,
        "chapter_count": chapter_count,
        "valid_chapter_ids": valid_chapter_ids,
    }

    outline_system_prompt = process_inputs.build_prompt(generation_mode, 'Report_outline_system')
    outline_user_prompt = process_inputs.build_prompt(
        generation_mode,
        'Report_outline_user',
        **user_kwargs
    )

    temperature = 0.9
    outline_response = await llm_call(outline_system_prompt, outline_user_prompt, temperature)
    outline_text, model, pdf_annotations = outline_response

    if outline_text is None:
        return None, None
    if outline_text == "Failed to generate due to error in API call":
        return None, None

    print("*** OUTLINE TEXT:" + outline_text + "   ****")  # DEBUG
    data = try_json_load(outline_text)

    if "target_word_count" not in data:
        data["target_word_count"] = report_target_wc

    outline = parse_outline(data)

    info(f"Outline received: {outline.topic} | Sections = {len(outline.outline_sections)}. Model: {model}")

    outline.word_count_target = report_target_wc

    within, total_est = outline_sum_within_tolerance(outline, report_target_wc)

    retries_left = OUTLINE_RETRIES
    revised_target_wc = report_target_wc

    while not within and retries_left > 0:
        info(
            f"Outline total {total_est} vs target {report_target_wc} "
            f"(±{int(OUTLINE_TOLERANCE * 100)}%) -> revising..."
        )

        revised_target_wc = int(revised_target_wc * 1.15)
        user_kwargs["report_target_wc"] = revised_target_wc

        print("Revised user kwarg report_target_wc: " + str(user_kwargs["report_target_wc"]))  # DEBUG

        outline_user_prompt = process_inputs.build_prompt(
            generation_mode,
            'Report_outline_user',
            **user_kwargs
        )

        outline_response = await llm_call(outline_system_prompt, outline_user_prompt, temperature)
        outline_text, model, pdf_annotations = outline_response

        if outline_text is None or outline_text == "Failed to generate due to error in API call":
            return None, None

        data = try_json_load(outline_text)
        if "target_word_count" not in data:
            data["target_word_count"] = report_target_wc

        outline = parse_outline(data)
        outline.word_count_target = report_target_wc

        within, total_est = outline_sum_within_tolerance(outline, report_target_wc)
        retries_left -= 1

    if not within:
        warn(f"Outline still off target after retries: total sections={total_est}, target={report_target_wc}")

    return outline, pdf_annotations


async def revise_outline_to_fit_target(  # not currently used for technical book summaries
        process_inputs: InputManifest,
        outline: Outline,
        report_target_wc: int,
        generation_mode: str,
        outline_system_prompt: str
) -> Outline:
    info("Requesting outline revision to fit target word count...")
    outline_json = json.dumps(
        {
            "topic": outline.topic,
            "target_word_count": report_target_wc,
            "outline_sections": [
                {
                    k: v
                    for k, v in {
                    "section_number": s.section_number,
                    "section_title": s.section_title,
                    "allocated_word_count": s.allocated_word_count,
                    "purpose": s.purpose,
                    "chapter_mapping": s.chapter_mapping,
                    "sub_sections": s.sub_sections,
                    "key_technical_requirements": s.key_technical_requirements,
                    "non_obvious_insights": s.non_obvious_insights
                }.items()
                    if v is not None
                }
                for s in outline.outline_sections
            ],
        },
        ensure_ascii=False,
        indent=2,
    )

    # set the variables to pass to the prompt builder which do not come from the inputs manifest file
    user_kwargs = {"outline": Outline, "report_target_wc": report_target_wc}
    # call the prompt builder, tell it which base prompt template to use
    outline_revision_user_prompt = process_inputs.build_prompt(generation_mode, 'Report_outline_revision_user',
                                                      **user_kwargs)
    temperature = 0.9 # TODO: make this a control parameter in the control matrix file
    outline_text, model, annotations = await llm_call(outline_system_prompt, outline_revision_user_prompt, temperature)
    # Note: annotations variable is not used, just here to catch return values of llm_call
    data = try_json_load(outline_text)
    data["target_word_count"] = report_target_wc
    revised = parse_outline(data)
    info(f"Revised outline: sections={len(revised.outline_sections)} Model: {model}")
    return revised


async def generate_report_from_outline(
        process_inputs: InputManifest,
        generation_mode: str,
        outline: Outline,
        output_dir: str,
        report_base_filename: str,
        reference_material: Optional[List[Dict[str,str]]] = None,
        pdf_annotations: Optional[str] = None,
        flag_use_refs_only: Optional[bool] = 'n',
        max_concurrency: int = 3,
        verbose: bool = True
) -> tuple[str, bool, str]:
    """Generates the full report text based on a pre-existing Outline."""
    section_failure_flag = False # initialise
    section_results = [] # initialise
    previous_section_outline = "" # initialise
    for i, sec in enumerate(outline.outline_sections):
        current_section_result, section_failure_flag = await _generate_one_report_section_with_watchdog(process_inputs, generation_mode, outline, sec,
                                        i + 1, len(outline.outline_sections), reference_material, flag_use_refs_only,
                                        pdf_annotations, previous_section_outline,verbose=verbose)
        section_results.append(current_section_result)  # section text
        previous_section_outline = sec  # previous section outline
        #previous_section_info = current_section_result[1]   # previous section info

    cleaned_sections: List[str] = []
    failed_sections_count = 0
    for i, result in enumerate(section_results, start=1):
        # Check if it's actually a string AND meets criteria
        if isinstance(result, str) and word_count(result) > 0:
            cleaned_sections.append(result)
        else:
            failed_sections_count += 1
            # If it's an Exception or an empty string, handle it here
            raise RuntimeError(f"Section {i} failed generation (not present). Error/Result: {result}")
    if failed_sections_count > 0: section_failure_flag = True
    if section_failure_flag:
        err("One or more sections failed to generate properly (word count or file access issue).  Saving report for "
            "reference then exiting.")
    report_text = build_report(outline, cleaned_sections)
    report_wc = word_count(report_text)
    report_path = os.path.join(output_dir, f"{report_base_filename}_REPORT.txt")
    save_text(report_path, report_text)
    info(f"Saved report: {report_base_filename}_REPORT.txt (words={report_wc})")

    return report_text, section_failure_flag, report_path


async def _generate_one_report_section_with_watchdog(
        process_inputs: InputManifest,
        generation_mode: str,
        outline: Outline,
        section_outline: OutlineSection,  # object
        section_number: int,
        total_sections: int,
        references: Optional[List[Dict[str, str]]] = None,
        flag_use_refs_only: Optional[bool] = None,
        pdf_annotations: Optional[Dict] = None,
        previous_section_outline: Optional[OutlineSection] = None,
        verbose: bool = True
) -> tuple[str, bool]:  # return section text only
    section_title = section_outline.section_title
    # TODO: review parsing of outlines and outline sections, possibly add get_attr to classes
    model = "--"

    async def _inner():
        # The core logic: call the generator with its own word-count expansion retries
        return await generate_report_section_text(process_inputs, generation_mode, outline, section_outline, previous_section_outline,
                                           references, flag_use_refs_only, pdf_annotations, WORDCOUNT_FLOOR_RATIO, SECTION_RETRIES)

    delay = 1.0
    for attempt in range(SECTION_RETRIES_ON_FAIL + 1):
        if verbose:
            info(
                f"Section {section_number}/{total_sections} START: {section_title} (~{section_outline.allocated_word_count} words) - "
                f"API Call Attempt {attempt + 1}/{SECTION_RETRIES_ON_FAIL + 1}")
        try:
            # Wrap the generation in a hard timeout
            text, model, section_failure_flag = await asyncio.wait_for(_inner(), timeout=SECTION_WATCHDOG_SEC)

            # If successful, check if the content is substantial (i.e., not a failure)
            if word_count(text) > 0:
                if verbose:
                    info(f"Section {section_number}/{total_sections} DONE: {section_title} (words={word_count(text)}) Model: {model}")
                return text, section_failure_flag  # TODO: include section info to be passed to next section as context. Return is a tuple
            else:
                # This catches the case where generate_section_text returns "" as best effort
                raise RuntimeError(f"Section generation returned empty content. Model: {model}")

        except (asyncio.TimeoutError, RuntimeError, Exception) as e:
            # Handle specific timeout and generic error/runtime error
            is_timeout = isinstance(e, asyncio.TimeoutError)
            error_type = "Timeout" if is_timeout else "Unspecified Error in calling generate_report_section_text for section"

            if attempt < SECTION_RETRIES_ON_FAIL:
                warn(
                    f"Section {section_number}/{total_sections} {error_type}: {section_title}. "
                    f"Model: {model}. Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, BACKOFF_MAX_SEC)
            else:
                warn(
                    f"Section {section_number}/{total_sections} {error_type}: {section_title}. "
                    f"Max retries ({SECTION_RETRIES_ON_FAIL + 1}) exceeded. Model {model}. ")
                # Raise a specific exception so the caller (do_topic) knows this section failed
                raise RuntimeError(f"Section generation failed after max retries: {section_title}. Model {model}.") from e

    # Should be unreachable, but good practice
    raise RuntimeError(f"Section generation failed after all attempts: {section_title}")


async def generate_report_section_text(
        process_inputs: InputManifest,
        generation_mode: str,
        outline: Outline,
        section_outline: OutlineSection,
        previous_section_outline: Optional[OutlineSection] = None,
        reference_material: Optional[List[Dict[str, str]]] = None,
        flag_use_refs_only: Optional[bool] = None,
        pdf_annotations: Optional[Dict] = None,
        floor_ratio: float = WORDCOUNT_FLOOR_RATIO,
        retries: int = SECTION_RETRIES,
) -> tuple[str, str, bool] | tuple[LiteralString, str | Any, bool] | tuple[LiteralString | str, str | Any, bool]:

    # print("in function generate_report_section_text section: " + str(section_outline.section_title)) # DEBUG
    report_topic =  outline.topic
    report_target_word_count = outline.target_word_count
    # removed the section outline string section_outline_json as not used in the prompt.  Gemini says also dont pass full outline in prompt

    min_floor = int(section_outline.allocated_word_count * floor_ratio)
    # TODO: get snippet of last section/ or other info as per Gemini

    section_chapters_text = [] # initialise
    section_text = "Section failed to generate" # default
    model = "NA" # default and initialisation
    file_access_success_flag = False # initialise
    section_final_fail_flag = False # initialise

    if previous_section_outline:
        previous_section_outline_str = str(previous_section_outline)  #json.dumps was causing fatal error
        print("previous section outline: " + previous_section_outline_str[:30]) # DEBUG
    else:
        previous_section_outline_str = ""
    has_web_page, has_public_pdf, has_local_pdf = False, False, False # initialise

    # print("generate_report_section_text general set-up done")# DEBUG
    #print("reference_material for section " + section_outline.section_title + ":  " + str(reference_material)) # DEBUG
    # set prompts about reference material
    if reference_material: # TODO: wrap this in a separate function ?
        if section_outline.chapter_mapping: # there are chapters, therefore this must be a book, all items in references are chapters
            # (or the chapter summary used in the outline).
            # TODO: change chapters to section references, to handle case of a non-book topic which has an outline with
            #  section-specific references

            # Get mapping numbers from outline, search the reference material list for the matching chapters, put those file names
            # into a list which will be used to set the user prompt and passed in llm call

            # First check and handle cases where LLM has not followed chapter mapping formatting
            # TODO: do this in the outline parsing
            clean_chapter_mapping = []  # initialise
            for chapter in section_outline.chapter_mapping:
                if ',' not in chapter and not chapter.lower().startswith('chapters'):
                    # there is only one chapter given, e.g. 'Chapter 7', NOT 'Chapters 5, 7 , 8'
                    clean_chapter_mapping.append(chapter)
                else:   # LLM has returned several chapters in a single entry, e.g. 'Chapters 5, 7, 8'
                    numbers = re.findall(r'\d+', chapter) # regex finds all sequences of digits
                    # Separate into a list
                    section_chap_list =  [f"Chapter {num}" for num in numbers] # Result: ['Chapter 5', 'Chapter 6', 'Chapter 9']
                    for chap in section_chap_list:
                        clean_chapter_mapping.append(chap)
            # Now do the matching between the outline listed chapters for the section and the file names
            section_chapters = [] # initialise
            for chapter in clean_chapter_mapping:
                chapter_match_count = 0
                for filename in reference_material:
                    # print("***chapter: " +  str(chapter)) # DEBUG
                    # print("***filename: " + str(filename['value'])) # DEBUG
                    chapter_no = chapter.lower() + "_" # TODO: this is brittle
                    if chapter_no in str(filename['value'].lower()):
                        section_chapters.append({'value': filename['value'], 'type': 'local pdf'})
                        chapter_match_count += 1
                if chapter_match_count == 0:  #!= 1:
                    err(f"Error for Section {section_outline.section_number}. Required book chapter {chapter} from "
                        f"report outline not found in the list of filenames in the "
                        f"references list for this topic.  Skipping this section.")
                    print(f"Chapters for section as per outline: {section_outline.chapter_mapping}")
                    print(f"Chapter filenames per topic references list: {reference_material}")
                    # TODO: let the user choose the correct chapter filename
                    # Exit the function for this section, with default values of section_text and model
                    section_final_fail_flag = True
                    return section_text, model, section_final_fail_flag
            # check have same number of chapters in the outline and the new list
            print("***section_chapters: " + str(section_chapters))  # DEBUG
            if len(section_chapters) == len(section_outline.chapter_mapping):
                # then replace the references list (which has all chapters) with just the chapters relevant for the section
                # reference_material = section_chapters  # OLD WHEN PASSING FILES DIRECTLY FOR API TO PROCESS
                # New below to read text files for inclusion in prompt
                for item in section_chapters:
                    print("in for path in section chapters")
                    print("path:"+ str(item['value']))
                    clean_path_str = item['value'].strip()
                    path = Path(clean_path_str)
                    if not path.is_file():
                        print(f"Error: {clean_path_str} is not a valid file.")
                    with open(path, 'r', encoding='utf-8') as file:
                        print("opening file")
                        content = file.read()
                        print("file read successfully")
                        section_chapters_text.append(content)
                        print("successfully appended text")
                reference_material = None # ensure nothing will be based as files to API call
        else:  # there is ref material but no chapter numbers in the outline, this is not a book. Set flags for prompt construction
            if 'web page' in reference_material[1]: has_web_page = True
            if 'public pdf' in reference_material[1]: has_public_pdf = True
            if 'local pdf' in reference_material[1]: has_local_pdf = True
    else:  # no reference material, so will just use LLM knowledge, no action needed
        pass

    # Pass all the section variables in kwargs
    user_kwargs = {"report_topic": report_topic, "report_target_wc": report_target_word_count,
                   "section_number": section_outline.section_number,
                   "section_title": section_outline.section_title,
                   # previous_section_title:
                   # previous_non_obvious_insights:
                   "section_allocated_word_count": section_outline.allocated_word_count,
                   "section_purpose": section_outline.purpose,
                   "section_chapter_mapping": section_outline.chapter_mapping,
                   "section_sub_sections": section_outline.sub_sections,
                   "section_sub_sections_count": str(len(section_outline.sub_sections)),
                   "section_key_technical_requirements": section_outline.key_technical_requirements,
                   "section_non_obvious_insights": section_outline.non_obvious_insights,
                   "section_chapters_text": str(section_chapters_text),
                   "section_references": reference_material,
                   "section_min_wc_floor" : min_floor,
                   "has_web_page": has_web_page,
                   "has_public_pdf": has_public_pdf,
                   "has_local_pdf": has_local_pdf,
                   "previous_section_outline": previous_section_outline_str,
                   "file_access_failure_msg": LLM_FILE_ACCESS_FAILURE_MSG,
                   "generated_section_text_outside_wc": "",
                   "generated_section_wc":0,
                   "sub_section_target_paras_guide": "3-4" # number of paragraphs to generate in each sub section
                   }
    # call the prompt builder, tell it which base prompt template to use
    print("report section user_kwargs set")  # DEBUG
    section_system_prompt = process_inputs.build_prompt(generation_mode, 'Report_section_system')
    section_user_prompt = process_inputs.build_prompt(generation_mode, 'Report_section_user',
                                                      **user_kwargs)
    # TODO handle empty prompts returned as a result of error in the build_prompt()
    print(f"section_user_prompt: {section_user_prompt[0:250]}")  # DEBUG
    temperature = 1.1  # TODO: make this a control parameter in the control matrix file
    adjusted_min_floor = min_floor # initialise outside loop
    attempt = 1
    while attempt <= retries:
        print(f"Section {section_outline.section_number} {section_outline.section_title} LLM call attempt {attempt} of {retries}, starting ...")
        try:
            text, model, annotations = await llm_call(section_system_prompt, section_user_prompt, temperature,
                                     reference_material, pdf_annotations)
            # Note: annotations variable is not used, just here to catch return values from llm_call.
        except Exception as e:
            warn(f"Error with LLM call for generation section text, {e}")
            text = ""

        if section_text == "Failed to generate due to error in API call":
            print(f"Section {section_outline.section_number} {section_outline.section_title} failed to generate due to error"
                  f"in API call, exiting section generation.")
            section_final_fail_flag = True
            return section_text, model, section_final_fail_flag  # exit the loop and function
        section_text = (text or "").strip()
        wc = word_count(section_text)
        # check LLM did not report that it could not access files
        if not check_llm_file_access_error(section_text): # TODO: remove this now with local pdf processing ?
            file_access_success_flag = True
        max_floor = int(section_outline.allocated_word_count * 1.2) # TODO: temp workaround
        if min_floor <= wc <= max_floor and file_access_success_flag:  # Success
            return section_text, model, section_final_fail_flag  #  exit the loop and function
        elif wc < min_floor:  # wc too low for section, repeat the whole section generation with a higher wc target
            # Case where section is unfeasibly small, covers case where the check_llm_file_access_error() didn't work
            if wc < 50:
                if attempt == retries:
                    err(f"Section '{section_outline.section_title}' severely under length on final attempt,"
                        f" (probably failure to access files).")
                    section_final_fail_flag = True
                    return section_text, model, section_final_fail_flag
                else:
                    # file_access_success_flag = False # turned this off now using local text file processing
                    warn(
                        f"Section '{section_outline.section_title}' below floor ({wc} < {min_floor}). Retrying (attempt {attempt}/{retries})...")
                    attempt += 1
                    continue # just proceed to next attempt

            # Case where section too short but no file access problem detected, so  expand
            if wc < min_floor and file_access_success_flag == True:
                if attempt == retries:
                    err(f"Section '{section_outline.section_title}' below floor on final attempt. {wc} < {min_floor}")
                    section_final_fail_flag = True
                    return section_text, model, section_final_fail_flag
                else:
                    warn(f"Section '{section_outline.section_title}' below floor ({wc} < {min_floor}). Expanding (attempt {attempt}/{retries})...")
                    # UPDATED new expansion approach:
                    user_kwargs["generated_section_text_outside_wc"] = section_text
                    user_kwargs[("generated_section_wc")] = wc
                    section_user_prompt = process_inputs.build_prompt(generation_mode, 'Report_section_expansion_user',
                                                                      **user_kwargs)
                    attempt += 1
                    continue

            # Case where file access problem detected
            if not file_access_success_flag: # TODO: remove this now with local pdf processing ?
                if attempt == retries:
                    err(f"Section '{section_outline.section_title}' failed to access files on final attempt.")
                    section_final_fail_flag = True
                    return section_text, model, section_final_fail_flag
                else:
                    warn(f"Section '{section_outline.section_title}' LLM reported failed to access files. Retrying (attempt {attempt}/{retries})...")

            # section_user_prompt = process_inputs.build_prompt(generation_mode, 'Report_section_user', **user_kwargs)
        else: # wc over max_floor
            if attempt == retries:
                err(f"Section '{section_outline.section_title}'  over wordcount target on final attempt.")
                # section_final_fail_flag = True #TODO: should this be set?
                return section_text, model, section_final_fail_flag
            else: # proceed to next attempt of full section generation request to try and hit wc target
                # TODO: need compression logic here
                warn(f"Section '{section_outline.section_title}'  over wordcount target on attempt {attempt} of {retries}, retrying... ")
                # user_kwargs["sub_section_target_paras_guide"] = "2-3"  # We tell LLM to generate a lower number of paras per section
                user_kwargs["generated_section_wc"] = wc
                user_kwargs["generated_section_text_outside_wc"] = section_text
                section_user_prompt = process_inputs.build_prompt(generation_mode, 'Report_section_compression_user',
                                                                 **user_kwargs)
                attempt += 1
                continue
        attempt += 1
        # time.sleep(1)  # Pause execution

    return section_text, model, section_final_fail_flag  # best effort, this will be triggered if max retries reached in the loop and section_text
    # still under min_floor


def build_report(outline: Outline, section_texts: List[str]) -> str:
    # structure the returned sections with consistent titles, numbers, chapter mappings per outline
    # then join all together to make report
    parts = [outline.topic, ""]
    for sec, body in zip(outline.outline_sections, section_texts):
        sec_number_title = str(sec.section_number) + ". " + sec.section_title
        parts.append(sec_number_title)
        parts.append(str(sec.chapter_mapping))
        parts.append((body or "").strip())
        parts.append("")
    return "\n".join(parts).strip()


def get_existing_report(outdir: str, existing_report: str):
    # open report file and get text
    if existing_report[:-4] != '.txt':
        existing_report = existing_report + ".txt"
    file_path = os.path.join(outdir, existing_report)
    try:
        info(f"Opening existing report file {existing_report} in ...{outdir[:30]}")
        document_content = open(file_path, 'r', encoding='utf-8').read()
    except Exception as e:
        warn(f"Error opening report {file_path}, {e}")
        document_content = ""
    report_outline = extract_outline(document_content)

    return document_content, report_outline


async def generate_script_from_report(
        process_inputs: InputManifest,
        generation_mode: str,
        topic: str,
        report_text: str,
        base_name: str,
        target_wc: int,
        report_wc: int
) -> tuple[str, int]:
    """Orchestrates conversion script and applying all formatting/validation."""
    # 1. Generate the script
    script_text = await convert_report_to_script(process_inputs, generation_mode, topic, report_text,
                                                 target_wc=target_wc, report_wc=report_wc )

    # 2. Apply validation & quality checks
    script_wc = word_count(script_text)
    if not (int(target_wc * (1 - SCRIPT_WC_UNDER_MARGIN)) <= script_wc <= int(target_wc * (1 + SCRIPT_WC_OVER_MARGIN))):
        warn(f"Script outside WC range: {script_wc}")

    if analyze_sentence_length(script_text)[2] < SCRIPT_MIN_SENTENCE_LENGTH:
        warn(f"Script sentence length under minimum.")

    # 3. History-Specific Cleaning
    # TODO: which of these to apply needs to be controlled by generation mode
    script_text = correct_script_text(script_text)
    if generation_mode == 'history':
        script_text, _ = process_document_for_ssml(script_text)
        script_text, _ = replace_years_in_text(script_text)

    # 4. TTS Compliance
    long_sentences = count_long_sentences(script_text, SENTENCE_MAX_CHARS)
    if long_sentences > 0:
        warn(f"{base_name} has {long_sentences} sentences over the TTS limit.")

    return script_text, script_wc


async def convert_report_to_script(
        process_inputs: InputManifest,
        generation_mode: str,
        topic: str,
        report_text: str,
        target_wc: int,
        report_wc: int,
        floor_ratio: float = WORDCOUNT_FLOOR_RATIO,
        under_margin: float = SCRIPT_WC_UNDER_MARGIN,
        over_margin: float = SCRIPT_WC_OVER_MARGIN,
        retries: int = SCRIPT_RETRIES
) -> str:
    """
    Generates a script based on a report. Sets prompt variables, builds prompts. Triggers LLM API call within a retry
    loop, including checking that the received script is within wordcount bounds.
    :param process_inputs:
    :param generation_mode:
    :param topic:
    :param report_text:
    :param target_wc:
    :param report_wc:
    :param floor_ratio:
    :param under_margin:
    :param over_margin:
    :param retries:
    :return: script
    """

    info("Converting report to spoken-delivery script...")
    temperature = 1.1  # TODO: make this a control parameter in the control matrix file
    # Calculate word count bounds
    min_wc = int(target_wc * (1 - under_margin))
    max_wc = int(target_wc * (1 + over_margin))
    script = "" # initialise
    model = "NA" # initialise

    # Pass all the section variables in kwargs
    user_kwargs = {"script_topic": topic, "report_wc": report_wc,
                   "script_target_word_count": target_wc,
                   "script_min_wc": min_wc,
                   "script_max_wc": max_wc,
                   "report_text": report_text,
                   "generated_script_outside_wc": "",
                   "generated_script_wc": "",
                   }
    # call the prompt builder, tell it which base prompt template to use
    print("script user_kwargs set")  # DEBUG
    script_system_prompt = process_inputs.build_prompt(generation_mode, 'Script_system')
    script_user_prompt = process_inputs.build_prompt(generation_mode, 'Script_user',
                                                      **user_kwargs)
    # TODO handle empty prompts returned as a result of error in the build_prompt()
    print(f"script_user_prompt: {script_user_prompt[0:250]}")  # DEBUG

    attempt = 1
    while attempt <= retries:
        # Initial or revised generation call
        timeout = REQ_TIMEOUT_SEC + 30 if attempt == 1 else REQ_TIMEOUT_SEC
        if attempt == 1:
            info(f"Requesting script, initial attempt ({attempt}/{retries})...")
        try:
            script, model, annotations = await asyncio.wait_for(
                llm_call(script_system_prompt, script_user_prompt, temperature,
                         ), timeout=timeout)
            # Note: annotations variable is not used, just here to catch return values from llm_call.
        except asyncio.TimeoutError:
            warn(
                f"Script generation timed out after {timeout}s on attempt {attempt}; proceeding to next retry or failure.")
            # On timeout, the script is considered too short/empty, and we let the loop try again/fail
            script = ""
            continue
        except Exception as e:
            warn(f"Script generation failed with error on attempt {attempt}: {e}. Retrying.")
            script = ""
            continue  # To next retry or failure
        script = (script or "").strip()
        # Revision prompt logic
        script_wc = word_count(script)
        # TODO: the wc limits (as % of target) for each check condition should be set in the generation mode matrix so this
        #    code is flexible to trigger different actions for different modes
        if script_wc < min_wc*.95: # word count is more than 80% of min, don't need to include Report in prompt
        # Note, accept wc 5% below min in order to avoid expansion tries
            if attempt == retries:
                warn(f"Script below target bounds after {retries} attempts: got {script_wc}, want {min_wc}-{max_wc}. Model: {model}")
                return script
            user_kwargs['script_target_word_count'] = str(target_wc * 1.2) # arbitrary target
            # TODO: need dedicated script expansion prompt which is a modified version of the standard user prompt focusing on
            #  length over style etc
            info(f"Script below floor ({script_wc} < {min_wc}). Requesting expansion (attempt {attempt}/{retries})...")
        elif script_wc < min_wc*0.8: # word count less than 80% of min, need to include report in prompt
            continue # this is a placeholder for other modes (other podcast types)
        elif script_wc > max_wc*1.05: # 5% margin to avoid condense re-tries
            if attempt == retries:
                warn(f"Script over target bounds after {retries} attempts: got {script_wc}, want {min_wc}-{max_wc}. Model: {model}")
                return script
            user_kwargs['generated_script_outside_wc'] = script
            user_kwargs['generated_script_wc'] = script_wc
            script_user_prompt = process_inputs.build_prompt(generation_mode, 'Script_condense_user',
                                                             **user_kwargs)
            info(f"Script over ceiling ({script_wc} > {max_wc}). Requesting condensation (attempt {attempt}/{retries})...")
        else:
            info(f"Script generation done (words={script_wc}; target={target_wc}; bounds={min_wc}-{max_wc}) Model: {model}.")
            return script
        attempt += 1
    # return script  # Return best effort, even if it failed the final check
    return script


async def generate_script_from_outline(
        generation_mode: str,
        topic: str,
        report_text: str,
        outline: Outline,
        script_instructions_gemini: str,
        script_instructions_claude: str,
        base_name: str,
        target_wc: int,
        report_wc: int
) -> str:
    """Creates script from an outline (not from report."""

#TODO:  take generation category/ mode as input, generate prompts and instructions conditionally
#       first construct anchor
#       then generate script outline
#       then generate script
#       do standard script checks
#       save script


async def generate_podcast_description(
        process_inputs: InputManifest,
        generation_mode: str,
        topic: str,
        outline: dict,  # uses OUTLINE ONLY, NOT REPORT TEXT, to save on tokens
        max_retries: int = 3,
) -> str:
    """Generates a 12-25 word single-sentence description."""
    info("Generating 12-25 word podcast description...")
    # Pass all the section variables in kwargs
    user_kwargs = {"topic": topic,
                   "outline": outline
                   }
    # call the prompt builder, tell it which base prompt template to use
    print("description user_kwargs set")  # DEBUG
    description_system_prompt = process_inputs.build_prompt(generation_mode, 'Description_system')
    description_user_prompt = process_inputs.build_prompt(generation_mode, 'Description_user',
                                                     **user_kwargs)

    attempt = 0
    while attempt <= max_retries:
        attempt += 1
        try:
            # Use a slightly shorter timeout for this single call
            desc_response = await asyncio.wait_for(llm_call(description_system_prompt, description_user_prompt),
                timeout=REQ_TIMEOUT_SEC
            )
            #print(desc_response)
            desc_raw = desc_response[0]
            desc_clean = desc_raw.strip().replace('\n', ' ').strip()
            wc = word_count(desc_clean)
            if 12 <= wc <= 30:
                info(f"Description generated: '{desc_clean[:50]}'... ({wc} words).")
                return desc_clean
            else:
                warn(f"Description failed word count: '{desc_clean}' ({wc} words). Retrying...")
                # just try again
                continue
        except asyncio.TimeoutError:
            warn(f"Description generation timed out on attempt {attempt}.")
        except Exception as e:
            warn(f"Description generation failed with error on attempt {attempt}: {e}.")

        await asyncio.sleep(min(2 ** attempt, BACKOFF_MAX_SEC))  # Wait before retrying

    warn("Failed to generate description within word count after max retries. Returning empty string.")
    return ""


def correct_script_text(text: str) -> str:
    """
    Applies final cleaning steps to the generated script text:
    1. Removes specified markdown characters (*, **, #) and abreviations with full stops (St.).
    2. Replaces a common LLM phrase ('let's quickly') with a preferred alternative ('let's briefly').
    """
    if not text:
        return ""

    corrected_text = text

    # Rule 1: Find and delete any occurrence of characters *, **, or #.
    # We remove '**' first to avoid leaving orphaned '*' characters.
    corrected_text = corrected_text.replace('**', '')
    corrected_text = corrected_text.replace('*', '')
    corrected_text = corrected_text.replace('#', '')
    corrected_text = corrected_text.replace('<break="0.5s"/>', '<break time="0.5s"/>')
    corrected_text = corrected_text.replace('<break="1s"/>', '<break time="1s"/>')
    corrected_text = corrected_text.replace('<break="2s"/>', '<break time="2s"/>')
    corrected_text = corrected_text.replace('St.', 'Saint ')

    # Rule 3: Replace occurrences of the text 'let's quickly' with 'let's briefly'.
    # Note: Using case-insensitive replacement (re.IGNORECASE) for robustness.
    corrected_text = re.sub(
        r"et[’']s quickly",
        "et's briefly",
        corrected_text,
        flags=re.IGNORECASE
    )
    return corrected_text


def count_long_sentences(text: str, max_chars: int = SENTENCE_MAX_CHARS) -> int:
    """
    Detects and counts sentences over a character limit
    (which will cause issues in later TTS processing).
    Splits the text into sentences with sentence-ending punctuation (., ?, !).
    Returns count of sentences over limit
        """
    if not text:
        print("No valid text for checking sentence lengths.")
        return 0

    # 1. Split text into sentences (including the delimiter)
    sentence_delimiters = r'([.?!])\s+'
    # re.split returns the captured delimiters, e.g., ['Sentence 1', '.', 'Sentence 2', '!']
    sentences = [piece.strip() for piece in re.split(sentence_delimiters, text) if piece.strip()]

    long_sentence_counter = 0
    # 2 Since we capture the delimiter, we process the list in pairs (sentence + delimiter)
    for i in range(0, len(sentences), 2):
        sentence_text = sentences[i]
        delimiter = sentences[i + 1] if i + 1 < len(sentences) else ""
        # Reconstruct the full sentence with its delimiter and a trailing space
        full_sentence = f"{sentence_text}{delimiter} " if delimiter else sentence_text

        # 2. Check if the current chunk can hold the next whole sentence
        if len(full_sentence) > max_chars:
            long_sentence_counter += 1

    return long_sentence_counter


# ------------------------- Files & IO -------------------------

def ensure_outdir(path: str):
    os.makedirs(path, exist_ok=True)

def save_text(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# ------------------------- Per-Row Processing (async) -------------------------

def build_base_filename(id_str: Optional[str], category: Optional[str], topic: str, ts_name: str) -> str:
    """Compose 'ID_Category_Topic_Date' with safe components; fallback to 'NA' if missing."""
    safe_id = sanitize_filename_component(id_str) if id_str else "NA"
    safe_cat = sanitize_filename_component(category) if category else "NA"
    safe_topic = sanitize_filename_component(topic)
    return f"{safe_id}_{safe_cat} {safe_topic} {ts_name}"


async def process_row(
        generation_mode: str,
        topic: str,
        subtopics: Optional[str],
        target_wc: int,
        guidelines: Optional[str],
        existing_report: str,
        outdir: str,
        rep_actual_wc: Optional[int],
        row_id: Optional[str] = None,
        category: Optional[str] = None,
        reference_material: Optional[List[Dict[str,str]]] = None,
        flag_use_refs_only: Optional[bool] = None,
        max_concurrency: int = 3,
        verbose: bool = True
) -> Tuple[str, str, int, str]:  # Now returns (report_path, script_path, podcast_description)
    """
    Orchestrates the entire generation process for one row read from the topics csv. Covers outline, report, script,
    and description in sequence, depending on generation mode matrix. Also initialises the generation mode matrix and
    the process inputs matrix as objects.
    Returns the saved report path and script paths, plus the script word count and the description for updating into
    the topics csv by the run_all function.
    :param generation_mode: from topics csv, used for matrix lookup
    :param topic: from topics csv
    :param subtopics: optional, from topics csv
    :param target_wc: from topics csv
    :param guidelines: optional,from topics csv
    :param existing_report: optional,from topics csv
    :param outdir:
    :param rep_actual_wc: from topics csv
    :param row_id: from topics csv
    :param category: from topics csv
    :param reference_material: file paths, from topics csv, previously put into a single list
    :param flag_use_refs_only: from topics csv
    :param max_concurrency:
    :param verbose:
    :return: report path, script path, script_wc, description
    """

    # --- 1. SETUP & INITIALIZATION ---
    control_matrix =  ModeMatrix(os.path.join(PODCAST_GENERATOR_DIR,"/reference files/generation_mode_matrix.csv"))
    process_inputs = InputManifest(os.path.join(PODCAST_GENERATOR_DIR,"/reference files/inputs_manifest.csv"))
    start_topic = time.monotonic()
    ts_name = timestamp_str()
    base_name = build_base_filename(row_id, category, topic, ts_name)

    info(f"=== TOPIC START: ID={row_id or 'NA'} {topic[:60]}... ===")
    if subtopics:
        info(f"Sub-topics: {subtopics[:60]}...")

    # --- 2. WRAPPER FOR WATCHDOG ---
    async def _run_pipeline():
        """The actual sequence of tasks."""

        # STEP: 1 OUTLINE. Generate Outline (with potential revisions):
        outline, pdf_annotations = None, None # initialise
        if control_matrix.get_mode_tasks(generation_mode, 'Report Outline') == 'y':
            if not existing_report:
                report_target_wc = int(target_wc * 1.1)  # ** INFLATE Target Word Count for report, as same target_wc is used for script
                # and script tends to compress report because of language guidelines
                outline, pdf_annotations = await generate_report_outline(process_inputs, generation_mode, topic, report_target_wc,
                                                                         subtopics, guidelines,reference_material, flag_use_refs_only)
                if outline is None:
                    err('Outline generation failed, exiting.')
                    sys.exit()
            else:
                pass
                # TODO: handle case where outline to be extracted from existing report

        # STEP 2: REPORT.  Generate Report sections (concurrently), assemble into Report and save:
        report_text = None # initialise
        section_failed_flag = False # initialise
        if control_matrix.get_mode_tasks(generation_mode, 'Report') == 'y':
            if not existing_report:
                if outline:
                    report_text, section_failed_flag, report_path = await generate_report_from_outline(process_inputs,
                    generation_mode, outline, outdir, base_name, reference_material, pdf_annotations, flag_use_refs_only)
                else:
                    err(f"No outline available to generate report for topic {topic}. ")
                    report_text = ""
            else:  # Case there is an existing report
                report_text, outline = get_existing_report(outdir, existing_report)
                report_path = ""  # this is included in the function return, so set to empty and handle later during saving
            # report_wc = rep_actual_wc or word_count(report_text)
            if section_failed_flag:
                err(f"One or more sections failed in report, ending process.")
                sys.exit() # One or more sections failed. Stop the process after report has been saved

        # STEP 3: SCRIPT and DESCRIPTION
        # TODO: Target word count for script is the 'Target Wordcount' from CSV, not the report's actual WC.
        if control_matrix.get_mode_tasks(generation_mode, 'Script') == 'y':
            # Option - Generate Script from Report
            if report_text:
                report_wc = rep_actual_wc or word_count(report_text)
                script_text, script_wc = await generate_script_from_report(process_inputs, generation_mode, topic, report_text,
                                                                           base_name, target_wc=target_wc, report_wc=report_wc)
                script_path = os.path.join(outdir, f"{base_name}_SCRIPT.txt")
                save_text(script_path, script_text)
                info(f"Saved script: {script_path} (words={script_wc})")
            else: # no report
                err("No report available for script generation. Exiting.")
                sys.exit()
                # Option - Generate Script from a Script Outline
                #await generate_script_from_outline()
            if script_text: podcast_description = await generate_podcast_description(process_inputs, generation_mode,
                                                                                     topic, outline)
        return report_path, script_path, script_wc, podcast_description

    # --- 3. EXECUTION WITH WATCHDOG & ERROR HANDLING ---
    try:
        # Global timeout for the entire topic process
        topic_result = await asyncio.wait_for(_run_pipeline(), timeout=TOPIC_WATCHDOG_SEC)
        dur = time.monotonic() - start_topic
        info(f"=== TOPIC DONE: {topic} in {dur:.1f}s ===")
        # return topic_result
    except asyncio.TimeoutError:
        warn(f"TOPIC {topic} TIMEOUT after {TOPIC_WATCHDOG_SEC}s.")
        # Write partial markers so you know where it stopped
        partial_marker = os.path.join(outdir, f"{base_name}_PARTIAL.txt")
        save_text(partial_marker, f"Topic timed out after {TOPIC_WATCHDOG_SEC}s.")
        # Return partial marker paths and an empty description
        return partial_marker, partial_marker, 0, ""
    except RuntimeError as e:
        # Catches the "Section failed" error raised inside generate_report_from_outline
        warn(f"TOPIC ABORTED: section failure in {topic} | Error: {e}")
        # Write a failure marker
        failure_marker = os.path.join(outdir, f"{base_name}_FAILED.txt")
        save_text(failure_marker, f"Topic aborted due to critical section generation failure.")
        # Return failure marker paths and an empty description
        return failure_marker, failure_marker, 0, ""
    except Exception as e:
        # Catch-all for unexpected code errors
        err(f"UNEXPECTED ERROR in {topic}: {str(e)}")
        traceback.print_exc()  # Useful for debugging new modular code
        return "ERROR", "ERROR", 0, ""

    duration = time.monotonic() - start_topic
    info(f"=== TOPIC DONE: {topic} in {duration:.1f}s ===")
    return topic_result


# ------------------------- CSV Reading & CLI -------------------------

def clean_value(value: str) -> str:
    """Replaces non-standard characters in a string based on the map."""
    cleaned = value
    for char, replacement in NON_STANDARD_CHAR_MAP.items():
        cleaned = cleaned.replace(char, replacement)
    # Optional: Remove any remaining non-ASCII characters that might be problematic
    # You might comment this out if you need to preserve certain foreign characters.
    # cleaned = ''.join(c for c in cleaned if ord(c) < 128)
    return cleaned


def read_csv(path: str) -> Tuple[List[Dict[str, str]], List[str]]:
    rows = []
    fieldnames = []
    # 1. Use 'encoding="utf-8-sig"' and 'errors="replace"'
    # The 'replace' argument will substitute any invalid character with
    # the Unicode replacement character ('') instead of crashing.
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames

            for r in reader:
                cleaned_row = {}
                for key, value in r.items():
                    # Check if the key/value pair is not None before cleaning
                    if key is not None and value is not None:
                        # 2. Clean both the key (header) and the value
                        cleaned_key = clean_value(key.strip())
                        cleaned_value = clean_value(value)
                        cleaned_row[cleaned_key] = cleaned_value
                rows.append(cleaned_row)

    except UnicodeDecodeError as e:
        # A fallback for much older/non-standard files, though 'errors="replace"'
        # should catch most issues.
        raise IOError(f"Failed to read CSV due to severe encoding issue: {e}. Try saving the file as UTF-8.")

    # Required columns remain Topic + TargetWordCount; others are optional.
    required = {"Topic", "Target Wordcount"}
    # The header must be cleaned before checking against the required set
    header = set([c.strip() for c in fieldnames]) if fieldnames else set()

    # Use the cleaned headers from the row data for validation, as the original
    # fieldnames from DictReader might contain uncleaned headers.
    if rows and fieldnames:
        # We need to rely on the *cleaned* keys for validation
        first_row_keys = set(rows[0].keys())

        # Check if the cleaned required columns are present
        if not required.issubset(first_row_keys):
            raise ValueError(
                "CSV must have columns: 'generation_mode', 'Topic' and 'Target Wordcount'. Optional: 'Report Actual WC','Actual Wordcount', 'Sub-topics', 'ID', "
                "'Category', 'Guidelines', 'Podcast Description'. 'Existing Report File Name'")

    return rows, fieldnames


def write_csv(path: str, rows: List[Dict[str, str]], fieldnames: List[str]):
    # Ensure 'Podcast Description' is in fieldnames if it's a new column
    if 'Podcast Description' not in fieldnames:
        fieldnames.append('Podcast Description')
    if 'Actual Wordcount' not in fieldnames:
        fieldnames.append('Actual Wordcount')
    if 'Report Actual WC' not in fieldnames:
        fieldnames.append('Report Actual WC')

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    info(f"Updated CSV saved to {path} with {len(rows)} rows.")


async def run_all(
        csv_path: str,
        outdir: str,
        max_concurrency: int,
        quiet: bool,
        no_preview: bool,
):
    ensure_outdir(outdir)
    original_rows, fieldnames = read_csv(csv_path)
    if not no_preview and HAS_PANDAS:
        try:
            df = pd.read_csv(csv_path)
            info(f"Loaded {len(df)} rows from {csv_path}. Columns: {list(df.columns)}")
        except Exception:
            pass

    # Use a copy of the rows to modify with the description
    modified_rows = original_rows.copy()

    for idx, r in enumerate(modified_rows, start=1):
        topic = (r.get("Topic") or "").strip()
        # TODO: in later iteration for books automatically get topic from the book file or book metadata and prompt user to confirm
        if not topic:
            warn(f"--- Row {idx}/{len(modified_rows)} --- [SKIP] Empty Topic row")
            continue
        row_id = (r.get("ID")).strip().lower()
        if row_id == "ignore" or row_id == "skip":  # for rows kept for later reference etc, marked to skip
            continue
        try:
            target_wc = int((r.get("Target Wordcount") or "").strip())
        except Exception:
            raise ValueError(f"Invalid Target Wordcount for topic '{topic}': {r.get('Target Wordcount')}")
        try:
            if r.get("Report Actual WC"):
                report_actual_wc = int(r.get("Report Actual WC").strip())
            else:
                report_actual_wc = ""
        except Exception:
            raise ValueError(f"Invalid Report Actual Wordcount for topic '{topic}': {r.get('Report Actual WC')}")
        subtopics = (r.get("Sub-topics") or "").strip() or None
        row_id = (r.get("ID") or "").strip() or None
        category = (r.get("Category") or "").strip() or None
        generation_mode = (r.get("generation_mode") or "").strip().lower()
        if not generation_mode:
            warn(f"--- Row {idx}/{len(modified_rows)} --- No category given, defaulting to history podcast.")
            generation_mode = "History"
            continue
        guidelines = (r.get("Guidelines") or "").strip() or None
        existing_report = (r.get("Existing Report File Name")).strip() or None
        web_page_references = (r.get("Web Page References")).strip().split(";") or None
        public_pdf_references = (r.get("Public PDF References")).strip().split(";") or None
        local_pdf_references = (r.get("Local PDF References")).strip().split(";") or None
        flag_use_refs_only = (r.get("Use References Only")).strip().lower() or None
        # set Boolean value of flag for making use of reference material exclusively
        references_list = []
        for item in web_page_references:
            references_list.append({'value': item, 'type': 'web page'})
        for item in public_pdf_references:
            references_list.append({'value': item, 'type': 'public pdf'})
        for item in local_pdf_references:
            references_list.append({'value': item, 'type': 'local pdf'})
        if flag_use_refs_only in ["yes", "y", "true", "x", "1"]:
            flag_use_refs_only = True
        else: flag_use_refs_only = None
        #info(
         #   f"---Topics Row {idx}/{len(modified_rows)} ID={row_id or 'NA'} | Topic={topic[50:]}")
        # Skip if 'Podcast Description' already exists and is non-empty
        # if r.get('Podcast Description', '').strip():
          #  info("Skipping generation for this row: 'Podcast Description' already exists.")
           # continue

        try:
            _, _,script_wordcount, podcast_description = await process_row(
                topic=topic,
                subtopics=subtopics,
                guidelines=guidelines,
                existing_report = existing_report,
                target_wc=target_wc,
                outdir=outdir,
                rep_actual_wc = report_actual_wc,
                row_id=row_id,
                category=category,
                generation_mode=generation_mode,
                reference_material=references_list,
                flag_use_refs_only = flag_use_refs_only,
                max_concurrency=max_concurrency,
                verbose=not quiet
            )
            # TODO Need to break the loop if process_row encounters an empty section somehow
            # Update the row dictionary with the new description and script actual wordcount
            # print("Podcast description to be saved: " + podcast_description)
            modified_rows[idx - 1]['Podcast Description'] = podcast_description
            modified_rows[idx - 1]['Actual Wordcount'] = str(script_wordcount)

        except Exception as e:
            err(f"Topic '{topic}' failed: {e}")
            print("--- FULL TRACEBACK ---")
            traceback.print_exc()
            # Continue to next topic

    # Write all rows (including updates or unchanged) back to the original CSV
    write_csv(csv_path, modified_rows, fieldnames)


def main():
    parser = argparse.ArgumentParser(description="Async Gemini pipeline: reports + audio scripts (Free Tier friendly).")
    parser.add_argument("--csv", required=True,
                        help="CSV path (Topic, TargetWordCount[, Sub-topics, ID, Category, Guidelines, Podcast Description])")
    parser.add_argument("--outdir", required=True, help="Output directory")
    parser.add_argument("--max_concurrency", type=int, default=3, help="Max parallel section generations per topic")
    parser.add_argument("--no_preview", action="store_true", help="Skip CSV preview (pandas)")
    parser.add_argument("--quiet", action="store_true", help="Less verbose logging")
    args = parser.parse_args()

    asyncio.run(run_all(
        csv_path=args.csv,
        outdir=args.outdir,
        max_concurrency=args.max_concurrency,
        quiet=args.quiet,
        no_preview=args.no_preview,
    ))


if __name__ == "__main__":
    main()