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
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Coroutine
from openrouter import OpenRouter
from typing_extensions import LiteralString

# ===================== Tunables (env overrides) =====================

REQ_TIMEOUT_SEC = int(os.getenv("LLM_REQ_TIMEOUT_SEC", "180"))  # each LLM request
ACQUIRE_MAX_WAIT_SEC = int(os.getenv("RATE_ACQUIRE_MAX_WAIT_SEC", "90"))  # max wait before heartbeat
SECTION_WATCHDOG_SEC = int(os.getenv("SECTION_WATCHDOG_SEC", "240"))  # one section
TOPIC_WATCHDOG_SEC = int(os.getenv("TOPIC_WATCHDOG_SEC", "3600"))  # whole topic
BACKOFF_MAX_SEC = int(os.getenv("BACKOFF_MAX_SEC", "8"))
SECTION_RETRIES_ON_FAIL = int(os.getenv("SECTION_RETRIES_ON_FAIL", "2")) # Max retries for a single section generation on timeout/failure

# Word Count Margins
WORDCOUNT_FLOOR_RATIO = float(os.getenv("WORDCOUNT_FLOOR_RATIO", "0.90"))  # Minimum acceptable ratio (0.90 = -10%)
SCRIPT_WC_UNDER_MARGIN = float(os.getenv("SCRIPT_WC_UNDER_MARGIN", "0.1"))  # % under target (0.10 = 10%)
SCRIPT_WC_OVER_MARGIN = float(os.getenv("SCRIPT_WC_OVER_MARGIN", "0.12"))  # % over target (0.10 = 10%)

# Rate limits (Free Tier – adjust if your project differs)
"""
RPM = int(os.getenv("GEMINI_LIMIT_RPM", "10"))
TPM = int(os.getenv("GEMINI_LIMIT_TPM", "250000"))
RPD = int(os.getenv("GEMINI_LIMIT_RPD", "250"))
"""

# Text references
report_prose_sample_path = "./Generate Text Scripts/reference files/JB_Bury_sample.txt"
script_style_sample_path = "./Generate Text Scripts/reference files/Doug_Metzger_sample.txt"

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
    print(f"[{ts()}] [WARN] {msg}", file=sys.stderr)


def err(msg: str):
    print(f"[{ts()}] [ERROR] {msg}", file=sys.stderr)

# ------------------------- OpenRouter Client (current APIs) -------------------------

class OpenRouterClient:
    """
    Supports:
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None
        self._setup()

    def _setup(self):
       self._client = OpenRouter(api_key=self.api_key)

    def generate(self, system_prompt: Optional[str], user_prompt: str, json_mode: bool = False) -> list[Any] | None:
        """
        Returns text content using the appropriate SDK call.
        """
        try:
            response = self._client.chat.send(
            # model="openai/gpt-4o",  # Specify the model you want to use
            messages=[
                {"role": "system",
                 "content": system_prompt
                 },
                {"role": "user",
                 "content": user_prompt
                 }
            ],
            stream=False,  # Set to True for streaming responses
            )
            # print(response.choices[0].message.content)
            # print(response.model)
            # print("generate")  # debug
            return [response.choices[0].message.content, response.model]

        except Exception as e:
            print(f"An error occurred: {e}")
            return None

async def llm_call(
        client: OpenRouterClient,
        system_prompt: Optional[str],
        user_prompt: str,
        json_mode: bool
) -> list:
    """LLM call with RPM/TPM gating, backoff, and a hard timeout."""
    # print("llm_call")  # debug
    return client.generate(system_prompt, user_prompt, json_mode)

# ------------------------- Data Structures & Helpers -------------------------

@dataclass
class OutlineSection:
    title: str
    character_count_estimate: int
    purpose: Optional[str] = None
    subsections: Optional[List[str]] = None


@dataclass
class Outline:
    title: str
    character_count_target: int
    sections: List[OutlineSection]


SECTION_RETRIES = 2
SCRIPT_RETRIES = 3  # Increased from 1 to 3 for revision attempts
OUTLINE_RETRIES = 2
OUTLINE_TOLERANCE = 0.12  # ±10%


def character_count(txt: str) -> int:
    return len(txt or "")


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
    for k in ["title", "character_count_target", "sections"]:
        if k not in o:
            return False, f"Missing key in outline: {k}"
    if not isinstance(o["sections"], list) or not o["sections"]:
        return False, "Outline.sections must be a non-empty list."
    for i, sec in enumerate(o["sections"]):
        for k in ["title", "character_count_estimate"]:
            if k not in sec:
                return False, f"Section {i} missing '{k}'."
    return True, "ok"


# ------------------------- Prompt Builders -------------------------

OUTLINE_SYSTEM = (
    "You are a meticulous research planner with narrative history skills. "
    "Return ONLY valid JSON with the schema keys: title, character_count_target, sections[]. "
    "Each section has: title, character_count_estimate, purpose (optional), subsections (optional list)."
)

OUTLINE_USER_TEMPLATE = """Create a detailed outline for a report.

Topic: "{topic}"
{maybe_subtopics}
Target total character count: {target_wc}
Guidelines to follow: {guidelines}

Constraints:
- Return ONLY valid JSON (no commentary).
- Follow this schema:
{schema_hint}
- Ensure total section character counts sum roughly to character_count_target (±10% tolerance).
- Choose sensible section boundaries and distribute characters to match the target.

Output: JSON only.
"""

OUTLINE_REVISION_USER_TEMPLATE = """Revise the following outline so that the sum of section character_count_estimate values
is within ±10% of character_count_target. Keep topic and overall logic unless adjustments
are required to meet the target. Return ONLY valid JSON.

Original outline JSON:
{outline_json}

Rules:
- Preserve clarity and coverage.
- Adjust section character_count_estimate values and/or section list if necessary.
- Ensure the final sum is within ±10% of character_count_target.
"""

report_prose_sample = load_text(report_prose_sample_path)

SECTION_SYSTEM = (f"You are a precise narrative history writer in Mandarin Chinese in simplified characters."
                  f"Write clear, well-structured prose that matches the requested character_count_estimate. "
                  f"Do not include headings unless asked; return plain text content for the section body."
                  f"Write to an HSK-6 level of vocablarly."
                  f"Do not use clichés, blanket generalizations, or overly optimistic conclusions."
                  f"Avoid use of LLM-typical phrases.")

SECTION_USER_TEMPLATE = """Write the content for ONE section of a report in Mandarin Chinese in simplified characters.

Section title: "{section_title}"
Requested character_count_estimate: {section_wc}
Purpose (if any): {section_purpose}

You are given the outline for the whole report (JSON below) to preserve coherence. Note, the outline is in English but
you are to output in Mandarin Chinese in simplified characters. 
Use consistent terminology. Some content overlap between sections is acceptable but avoid significant repetition.

Outline JSON:
{outline_json}

Rules:
- Output in Mandarin Chinese in simplified characters with HSK-6 level vocabulary
- Return plain text (no markdown headings).
- Avoid filler; be substantive and specific.
- Aim at {section_wc} characters (>= {min_floor} absolute minimum).
"""

script_style_sample = load_text(script_style_sample_path)

SCRIPT_SYSTEM = (
    "You are an expert instructional designer creating a spoken-delivery script in Mandarin Chinese in simplified characters "
    "optimised for audio learning."
)

SCRIPT_USER_TEMPLATE = """Transform the report below into a spoken-delivery script in Mandarin Chinese in simplified characters, following the given instructions. 
 The script length should be {target_character_count} characters long. 

=== REPORT START ===
{report_text}
=== REPORT END ===

=== SCRIPT INSTRUCTIONS START ===
{script_instructions}
=== SCRIPT INSTRUCTIONS END ===


Rules:
- Output in Mandarin Chinese in simplified characters at HSK-6 level vocabulary.
- Follow the structure and style requirements from the instructions.
- The script length should be {target_character_count} characters long. 
- Return the script as plain text.
"""

# New prompt for the podcast description
DESCRIPTION_SYSTEM = (
    "You are a skilled historical writer. Your task is to generate a short, interesting "
    "podcast episode description in Mandarin Chinese in simplified characters (HSK-6 level vocab) based on the provided report text."
)

DESCRIPTION_USER_TEMPLATE = """Generate a short, single-sentence podcast description in Mandarin Chinese in simplified characters for the report below.

Report Topic: "{topic}"

=== REPORT START ===
{report_text}
=== REPORT END ===

Rules:
- Generate Mandarin Chinese in simplified characters output, at HSK-6 level vocabulary. 
- The description must be a single, standalone sentence.
- The description must be up to 30 characters in length.
- The description should be engaging and accurately summarize the main subject and conflict of the report.
- Return ONLY the single sentence. Do not include any commentary, labels, or extra text.
"""


# ------------------------- Outline / Section / Script / Description Gen -------------------------

def parse_outline(data: Dict[str, Any]) -> Outline:
    ok, msg = validate_outline_struct(data)
    if not ok:
        raise ValueError(f"Invalid outline JSON: {msg}")
    sections = [
        OutlineSection(
            title=s["title"],
            character_count_estimate=int(s["character_count_estimate"]),
            purpose=s.get("purpose"),
            subsections=s.get("subsections"),
        )
        for s in data["sections"]
    ]
    return Outline(
        title=data["title"],
        character_count_target=int(data["character_count_target"]),
        sections=sections,
    )


def outline_sum_within_tolerance(outline: Outline, target_wc: int, tol: float = OUTLINE_TOLERANCE) -> Tuple[bool, int]:
    total = sum(s.character_count_estimate for s in outline.sections)
    lower = int(target_wc * (1 - tol))
    upper = int(target_wc * (1 + tol))
    return (lower <= total <= upper), total


async def generate_outline(
        client: OpenRouterClient,
        topic: str,
        subtopics_str: Optional[str],
        guidelines: Optional[str],
        schema_hint: str,
        target_wc: int,
) -> Outline:
    info(f"Requesting outline for topic: {topic}")
    maybe_sub = f'Sub-topics to include: "{subtopics_str}"' if subtopics_str else "No specific sub-topics provided."
    user_prompt = OUTLINE_USER_TEMPLATE.format(
        topic=topic,
        maybe_subtopics=maybe_sub,
        guidelines=guidelines,
        schema_hint=schema_hint,
        target_wc=target_wc,
    )
    txt, model = await llm_call(client, OUTLINE_SYSTEM, user_prompt, json_mode=True)
    data = try_json_load(txt)
    if "character_count_target" not in data:
        data["character_count_target"] = target_wc
    outline = parse_outline(data)
    info(f"Outline received: {outline.title} | sections={len(outline.sections)}. Model: {model}")
    return outline


async def revise_outline_to_fit_target(
        client: OpenRouterClient,
        outline: Outline,
        target_wc: int,
) -> Outline:
    info("Requesting outline revision to fit target character count...")
    outline_json = json.dumps(
        {
            "title": outline.title,
            "character_count_target": target_wc,
            "sections": [
                {
                    k: v
                    for k, v in {
                    "title": s.title,
                    "character_count_estimate": s.character_count_estimate,
                    "purpose": s.purpose,
                    "subsections": s.subsections,
                }.items()
                    if v is not None
                }
                for s in outline.sections
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    user_prompt = OUTLINE_REVISION_USER_TEMPLATE.format(outline_json=outline_json)
    txt, model = await llm_call(client, OUTLINE_SYSTEM, user_prompt, json_mode=True)
    data = try_json_load(txt)
    data["character_count_target"] = target_wc
    revised = parse_outline(data)
    info(f"Revised outline: sections={len(revised.sections)} Model: {model}")
    return revised


async def _generate_one_section_with_watchdog(
        client: OpenRouterClient,
        outline: Outline,
        section: OutlineSection,
        idx: int,
        n: int,
        verbose: bool = True,
) -> str:
    title = section.title
    model = "NA"

    async def _inner():
        # The core logic: call the generator with its own word-count expansion retries
        return await generate_section_text(client, outline, section)

    delay = 1.0
    for attempt in range(SECTION_RETRIES_ON_FAIL + 1):
        if verbose:
            info(
                f"Section {idx}/{n} START: {title} (~{section.character_count_estimate} characters) - API Call Attempt {attempt + 1}/{SECTION_RETRIES_ON_FAIL + 1}")

        try:
            # Wrap the generation in a hard timeout
            text, model = await asyncio.wait_for(_inner(), timeout=SECTION_WATCHDOG_SEC)

            # If successful, check if the content is substantial (i.e., not a failure)
            if character_count(text) > 0:
                if verbose:
                    info(f"Section {idx}/{n} DONE: {title} (characters={character_count(text)}) Model: {model}")
                return text
            else:
                # This catches the case where generate_section_text returns "" as best effort
                raise RuntimeError(f"Section generation returned empty content. Model: {model}")

        except (asyncio.TimeoutError, RuntimeError, Exception) as e:
            # Handle specific timeout and generic error/runtime error
            is_timeout = isinstance(e, asyncio.TimeoutError)
            error_type = "TIMEOUT" if is_timeout else "ERROR"

            if attempt < SECTION_RETRIES_ON_FAIL:
                warn(
                    f"Section {idx}/{n} {error_type} after {SECTION_WATCHDOG_SEC}s: {title}. Model {model}. Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, BACKOFF_MAX_SEC)
            else:
                warn(
                    f"Section {idx}/{n} {error_type} after {SECTION_WATCHDOG_SEC}s: {title}. Max retries ({SECTION_RETRIES_ON_FAIL + 1}) exceeded. Model {model}. ")
                # Raise a specific exception so the caller (do_topic) knows this section failed
                raise RuntimeError(f"Section generation failed after max retries: {title}. Model {model}.") from e

    # Should be unreachable, but good practice
    raise RuntimeError(f"Section generation failed after all attempts: {title}")


async def generate_section_text(
        client: OpenRouterClient,
        outline: Outline,
        section: OutlineSection,
        floor_ratio: float = WORDCOUNT_FLOOR_RATIO,
        retries: int = SECTION_RETRIES,
) -> tuple[LiteralString, Any] | tuple[LiteralString | str, Any]:
    outline_json = json.dumps(
        {
            "title": outline.title,
            "character_count_target": outline.character_count_target,
            "sections": [
                {
                    k: v
                    for k, v in {
                    "title": s.title,
                    "character_count_estimate": s.character_count_estimate,
                    "purpose": s.purpose,
                    "subsections": s.subsections,
                }.items()
                    if v is not None
                }
                for s in outline.sections
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    min_floor = int(section.character_count_estimate * floor_ratio)
    attempt = 0
    last_text = ""
    model = "NA"
    while attempt <= retries:
        user_prompt = SECTION_USER_TEMPLATE.format(
            section_title=section.title,
            section_wc=section.character_count_estimate,
            section_purpose=section.purpose or "N/A",
            outline_json=outline_json,
            min_floor=min_floor,
        )
        text, model = await llm_call(client, SECTION_SYSTEM, user_prompt, json_mode=False)
        last_text = (text or "").strip()
        wc = character_count(last_text)
        if wc >= min_floor:
            return last_text, model
        attempt += 1
        warn(f"Section '{section.title}' below floor ({wc} < {min_floor}). Expanding (attempt {attempt}/{retries})...")
        #TODO: change below prompt as API has no memory.  Check report text is included in prompt
        expand_msg = (
            f"A previous LLM API call generated the below text for a section of a report in Mandarin Chinese in simplified characters."
            f"The text is too short, being {wc} characters, below the minimum {min_floor} characters. "
            f"Please expand substantively to meet or exceed {min_floor} characters."
            f"Refer to the section text, the report outline, and the section title and purpose provided to you."
            f"Keep the section title and purpose."
            f"Add meaningful information , e.g. more detail on the topic. Do not add waffle, wordiness or repetition."
            f"Write in Mandarin Chinese in simplified characters at HSK-6 level.  "
            f"Previously generated section text:  "
        )
        text2, model = await llm_call(client, SECTION_SYSTEM, user_prompt + "\n\n" + expand_msg+ "\n" + last_text,
                                           json_mode=False)
        last_text = (text2 or "").strip()
        if character_count(last_text) >= min_floor:
            return last_text, model
    return last_text, model  # best effort


def build_report(outline: Outline, section_texts: List[str]) -> str:
    parts = [outline.title, ""]
    for sec, body in zip(outline.sections, section_texts):
        parts.append(sec.title)
        parts.append((body or "").strip())
        parts.append("")
    return "\n".join(parts).strip()


async def convert_report_to_script(
        client: OpenRouterClient,
        report_text: str,
        script_instructions: str,
        target_wc: int,
        under_margin: float = SCRIPT_WC_UNDER_MARGIN,
        over_margin: float = SCRIPT_WC_OVER_MARGIN,
        retries: int = SCRIPT_RETRIES,
) -> str:
    info("Converting report to spoken-delivery script...")

    # Calculate word count bounds
    min_wc = int(target_wc * (1 - under_margin))
    max_wc = int(target_wc * (1 + over_margin))

    base_user_prompt = SCRIPT_USER_TEMPLATE.format(
        script_instructions=script_instructions,
        report_text=report_text,
        target_character_count = target_wc,
        script_style_sample = script_style_sample
    )

    script = ""
    model = "NA"
    attempt = 0
    while attempt <= retries:
        attempt += 1
        current_prompt = base_user_prompt

        if script:
            # Revision prompt logic
            wc = character_count(script)
            if wc < min_wc:
                expand = (
                    f"An LLM just generated the below script, this is intended to be a spoken-word script in Mandarin Chinese in simplified characters for an informational podcast."
                    f"The script is based on the below report."
                    f"The LLM-generated script has {wc} characters which is below the minimum required character count of {min_wc}."
                    #f"(target {target_wc}, under-margin {under_margin * 100}%). "
                    "Your task is to 1) review the original report, 2) review the previously generated script, 3) review the"
                    f"script instructions, 3) re-write the script to meet the target character count of {target_wc}."
                    "Write in Mandarin Chinese in simplified characters at HSK-6 level"
                    "Preserve structure and pacing. Do not add commentary, just the revised script. "
                    "Do not add waffle or wordiness or repetition, use information from the report text such as additional detail. "
                )
                info(f"Script below floor ({wc} < {min_wc}). Requesting expansion (attempt {attempt}/{retries})...")
                current_prompt += (f"\n\n=== TASK ===\n{expand}\n\n=== REPORT AND SCRIPT INSTRUCTIONS START ==="
                                   f"\n{base_user_prompt}\n=== REPORT AND SCRIPT INSTRUCTIONS  END ==="
                                   f"\n\n=== PREVIOUS SCRIPT START ===\n{script}\n=== PREVIOUS SCRIPT END ===")
            elif wc > max_wc:
                condense = (
                    f"An LLM just generated the below script, this is intended to be a spoken-word script in Mandarin Chinese in simplified characters for an informational podcast."
                    f"The script is based on the below report."
                    f"The LLM-generated script has {wc} characters, which is above the maximum required character count of {max_wc}."
                    "Your task is to 1) review the original report, 2) review the previously generated script, 3) review the"
                    f"script instructions, 3) condense the previous script to stay below the maximum character count of {max_wc}."
                    # Note - this step tends to condense too much so just mention max_wc not target_wc.
                    #f"(target {target_wc}, over-margin {over_margin * 100}%). "
                    "Write in Mandarin Chinese in simplified characters at HSK-6 level."
                    "Preserve all key information and the required structure."
                    "Do not add commentary, just the revised script."
                )
                info(f"Script over ceiling ({wc} > {max_wc}). Requesting condensation (attempt {attempt}/{retries})...")
                current_prompt += (f"\n\n=== TASK ===\n{condense}\n\n=== REPORT AND SCRIPT INSTRUCTIONS START ==="
                                   f"\n{base_user_prompt}\n=== REPORT AND SCRIPT INSTRUCTIONS  END ==="
                                   f"\n\n=== PREVIOUS SCRIPT START ===\n{script}\n=== PREVIOUS SCRIPT END ===")

            else:
                info(f"Script generation done (characters={wc}; target={target_wc}; bounds={min_wc}-{max_wc}) Model: {model}.")
                return script

        # Initial or revised generation call
        timeout = REQ_TIMEOUT_SEC + 30 if attempt == 1 else REQ_TIMEOUT_SEC
        try:
            # Initial call timeout uses REQ_TIMEOUT_SEC + 30, subsequent revision calls use base REQ_TIMEOUT_SEC
            script, model = await asyncio.wait_for(
                llm_call(client, SCRIPT_SYSTEM, current_prompt, json_mode=False),
                timeout=timeout
            )
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

    # Final check after all retries
    wc = character_count(script)
    if min_wc <= wc <= max_wc:
        info(f"Script generation done (characters={wc}; target={target_wc}; bounds={min_wc}-{max_wc}). Model: {model}")
        return script
    else:
        warn(f"Script failed to meet target bounds after {retries + 1} attempts: got {wc}, want {min_wc}-{max_wc}. Model: {model}")
        return script  # Return best effort, even if it failed the final check


async def generate_podcast_description(
        client: OpenRouterClient,
        topic: str,
        report_text: str,
        max_retries: int = 3,
) -> str:
    """Generates a 12-25 word single-sentence description."""
    info("Generating podcast description...")
    user_prompt = DESCRIPTION_USER_TEMPLATE.format(
        topic=topic,
        report_text=report_text,
    )
    attempt = 0
    while attempt <= max_retries:
        attempt += 1
        try:
            # Use a slightly shorter timeout for this single call
            desc_response = await asyncio.wait_for(
                llm_call(client, DESCRIPTION_SYSTEM, user_prompt, json_mode=False),
                timeout=REQ_TIMEOUT_SEC
            )
            desc_raw = desc_response[0]
            desc_clean = desc_raw.strip().replace('\n', ' ').strip()
            wc = character_count(desc_clean)
            if 12 <= wc <= 25:
                info(f"Description generated: '{desc_clean}' ({wc} characters).")
                return desc_clean
            else:
                warn(f"Description failed character count: '{desc_clean}' ({wc} characters). Retrying...")
                # Add a note to the prompt for the next attempt
                user_prompt += (
                    f"\n\n=== REVISION TASK ===\n"
                    f"Your last attempt had {wc} characters. Please revise to be between 20 and 30 characters."
                )
        except asyncio.TimeoutError:
            warn(f"Description generation timed out on attempt {attempt}.")
        except Exception as e:
            warn(f"Description generation failed with error on attempt {attempt}: {e}.")

        await asyncio.sleep(min(2 ** attempt, BACKOFF_MAX_SEC))  # Wait before retrying

    warn("Failed to generate description within character count after max retries. Returning empty string.")
    return ""


def correct_script_text(text: str) -> str:
    """
    Applies final cleaning steps to the generated script text:
    1. Removes specified markdown characters (*, **, #).
    2. Ensures full-stops on full-caps section headings.
    3. Replaces a common LLM phrase ('let's quickly') with a preferred alternative ('let's briefly').
    """
    if not text:
        return ""

    corrected_text = text

    # Rule 1: Find and delete any occurrence of characters *, **, or #.
    # We remove '**' first to avoid leaving orphaned '*' characters.
    corrected_text = corrected_text.replace('**', '')
    corrected_text = corrected_text.replace('*', '')
    corrected_text = corrected_text.replace('#', '')
    corrected_text = corrected_text.replace('<break="1s"/>', '<break time="1s"/>')
    corrected_text = corrected_text.replace('<break="2s"/>', '<break time="2s"/>')

    # Rule 3: Replace occurrences of the text 'let's quickly' with 'let's briefly'.
    # Note: Using case-insensitive replacement (re.IGNORECASE) for robustness.
    """
    corrected_text = re.sub(
        r"et[’']s quickly",
        "et's briefly",
        corrected_text,
        flags=re.IGNORECASE
    )
    """

    # Rule 2: Ensure there is a full-stop at the end of each section heading (the full-caps headings).
    # Regex to find a line that:
    # 1. Starts at the beginning of a line (^)
    # 2. Contains 1 or more ALL CAPS characters, digits, spaces, common heading punctuation.
    # 3. Does NOT end with a period, exclamation mark, or question mark (negative lookbehind).
    # 4. Ends right before the line break ($)
    # The replacement adds a dot to the captured group (\1).
    corrected_text = re.sub(
        r'^([A-Z0-9\s,\'\"\(\)\-\/\&]+)(?<![\.\!\?])\s*$',
        r'\1.',
        corrected_text,
        flags=re.MULTILINE
    )

    return corrected_text


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
        client: OpenRouterClient,
        topic: str,
        subtopics: Optional[str],
        target_wc: int,
       # report_prose_sample: Optional[str],
        guidelines: Optional[str],
        outdir: str,
        schema_hint: str,
        script_instructions: str,
        row_id: Optional[str] = None,
        category: Optional[str] = None,
        max_concurrency: int = 3,
        verbose: bool = True,
) -> Tuple[str, str, str]:  # Now returns (report_path, script_path, podcast_description)
    start_topic = time.monotonic()
    ts_name = timestamp_str()
    base_name = build_base_filename(row_id, category, topic, ts_name)

    info(f"=== TOPIC START: {topic} | target={target_wc} | ID={row_id or 'NA'} | Category={category or 'NA'} ===")
    if subtopics:
        info(f"Sub-topics: {subtopics}")

    async def _do_topic():
        # 1) Outline (with potential revisions)
        outline = await generate_outline(client, topic, subtopics, guidelines, schema_hint, target_wc)
        outline.character_count_target = target_wc

        within, total_est = outline_sum_within_tolerance(outline, target_wc)
        retries_left = OUTLINE_RETRIES
        while not within and retries_left > 0:
            info(f"Outline total {total_est} vs target {target_wc} (±{int(OUTLINE_TOLERANCE * 100)}%) -> revising...")
            outline = await revise_outline_to_fit_target(client, outline, target_wc)
            outline.character_count_target = target_wc
            within, total_est = outline_sum_within_tolerance(outline, target_wc)
            retries_left -= 1

        if not within:
            warn(f"Outline still off target after retries: total sections={total_est}, target={target_wc}")

        info(
            f"Sections to generate: {len(outline.sections)} (sum={sum(s.character_count_estimate for s in outline.sections)})")

        # 2) Sections concurrently
        sem = asyncio.Semaphore(max_concurrency)

        async def _one(sec: OutlineSection, idx: int, n: int) -> str:
            async with sem:
                # NOTE: _generate_one_section_with_watchdog will now raise RuntimeError on final failure/timeout
                return await _generate_one_section_with_watchdog(client, outline, sec, idx, n, verbose=verbose)

        tasks = [asyncio.create_task(_one(sec, i + 1, len(outline.sections))) for i, sec in enumerate(outline.sections)]
        section_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures (exceptions or empty strings)
        cleaned_sections: List[str] = []
        all_sections_complete = True
        for i, res in enumerate(section_results, start=1):
            section_title = outline.sections[i - 1].title
            if isinstance(res, Exception):
                err(f"Section {i} FINAL FAILURE: '{section_title}' raised: {res}")
                cleaned_sections.append("")
                all_sections_complete = False
            elif not res or character_count(res) == 0:
                err(f"Section {i} FINAL FAILURE: '{section_title}' resulted in empty content.")
                cleaned_sections.append("")
                all_sections_complete = False
            else:
                cleaned_sections.append(res)

        if not all_sections_complete:
            # If any section failed, skip report/script creation and signal failure to the caller
            raise RuntimeError(
                "One or more sections failed generation or timeout after max retries. Skipping report/script.")

        # 3) Report (Only if all sections complete)
        report_text = build_report(outline, cleaned_sections)
        report_wc = character_count(report_text)
        report_path = os.path.join(outdir, f"{base_name}_REPORT.txt")
        save_text(report_path, report_text)
        info(f"Saved report: {report_path} (characters={report_wc})")

        # 4) Podcast Description (NEW STEP)
        podcast_description = await generate_podcast_description(client, topic, report_text)

        # 5) Script
        # NOTE: Target word count for script is the 'Target Wordcount' from CSV, not the report's actual WC.
        script_text = await convert_report_to_script(
            client, report_text, script_instructions, target_wc=target_wc
        )
        script_wc = character_count(script_text)
        min_script_wc = int(target_wc * (1 - SCRIPT_WC_UNDER_MARGIN))
        max_script_wc = int(target_wc * (1 + SCRIPT_WC_OVER_MARGIN))

        if not (min_script_wc <= script_wc <= max_script_wc):
            warn(f"Script under/over final target: got {script_wc}, want {min_script_wc}-{max_script_wc}")

        script_text = correct_script_text(script_text)
        script_path = os.path.join(outdir, f"{base_name}_SCRIPT.txt")
        save_text(script_path, script_text)
        info(f"Saved script: {script_path} (characters={script_wc})")

        return report_path, script_path, podcast_description

    # Topic watchdog
    try:
        res = await asyncio.wait_for(_do_topic(), timeout=TOPIC_WATCHDOG_SEC)
    except asyncio.TimeoutError:
        warn(f"TOPIC TIMEOUT after {TOPIC_WATCHDOG_SEC}s: {topic}")
        # Write partial markers so you know where it stopped
        partial_marker = os.path.join(outdir, f"{base_name}_PARTIAL.txt")
        save_text(partial_marker, f"Topic timed out after {TOPIC_WATCHDOG_SEC}s.")
        # Return partial marker paths and an empty description
        return partial_marker, partial_marker, ""
    except RuntimeError as e:
        # Handle the failure flag raised by _do_topic (due to empty section)
        warn(f"TOPIC ABORTED due to section failure: {topic} | Error: {e}")
        # Write a failure marker
        failure_marker = os.path.join(outdir, f"{base_name}_FAILED.txt")
        save_text(failure_marker, f"Topic aborted due to critical section generation failure.")
        # Return failure marker paths and an empty description
        return failure_marker, failure_marker, ""

    dur = time.monotonic() - start_topic
    info(f"=== TOPIC DONE: {topic} in {dur:.1f}s ===")
    return res


# ------------------------- CSV Reading & CLI -------------------------

# Modifed to return (rows, fieldnames) to enable writing back.
def read_csv(path: str) -> Tuple[List[Dict[str, str]], List[str]]:
    rows = []
    fieldnames = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for r in reader:
            rows.append(r)
    # Required columns remain Topic + TargetWordCount; others are optional.
    required = {"Topic", "Target Character Count"}
    header = set([c.strip() for c in (fieldnames)]) if fieldnames else set()
    if not required.issubset(header):
        raise ValueError("CSV must have columns: 'Topic' and 'Target Character Count'. Optional: 'Sub-topics', 'ID', "
                         "'Category', 'Guidelines', 'Podcast Description'.")
    return rows, fieldnames


def write_csv(path: str, rows: List[Dict[str, str]], fieldnames: List[str]):
    # Ensure 'Podcast Description' is in fieldnames if it's a new column
    if 'Podcast Description' not in fieldnames:
        fieldnames.append('Podcast Description')

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    info(f"Updated CSV saved to {path} with {len(rows)} rows.")


async def run_all(
        csv_path: str,
        outdir: str,
        model: str,
        # report_prose_sample: str,
        script_instructions_path: str,
        outline_schema_hint_path: str,
        max_concurrency: int,
        quiet: bool,
        no_preview: bool,
):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        err("Set OPENROUTER_API_KEY environment variable.")
        raise SystemExit(1)

    ensure_outdir(outdir)

    # report_prose_sample - load_text(report_prose_sample_path)
    script_instructions = load_text(script_instructions_path)
    outline_schema_hint_text = load_text(outline_schema_hint_path)

    # Compact schema hint for prompt
    try:
        _ = json.loads(outline_schema_hint_text)
        compact_schema_hint = json.dumps(
            {
                "title": "<string>",
                "character_count_target": "<int>",
                "sections": [
                    {
                        "title": "<string>",
                        "character_count_estimate": "<int>",
                        "purpose": "<string, optional>",
                        "subsections": ["<string>", "... (optional)"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception:
        compact_schema_hint = outline_schema_hint_text[:1000]

    original_rows, fieldnames = read_csv(csv_path)

    if not no_preview and HAS_PANDAS:
        try:
            df = pd.read_csv(csv_path)
            info(f"Loaded {len(df)} rows from {csv_path}. Columns: {list(df.columns)}")
        except Exception:
            pass

    client = OpenRouterClient(api_key=api_key)

    # Use a copy of the rows to modify with the description
    modified_rows = original_rows.copy()

    for idx, r in enumerate(modified_rows, start=1):
        topic = (r.get("Topic") or "").strip()
        if not topic:
            warn(f"--- Row {idx}/{len(modified_rows)} --- [SKIP] Empty Topic row")
            continue
        try:
            target_wc = int((r.get("Target Character Count") or "").strip())
        except Exception:
            raise ValueError(f"Invalid Target Character Count for topic '{topic}': {r.get('Target Character Count')}")
        subtopics = (r.get("Sub-topics") or "").strip() or None
        row_id = (r.get("ID") or "").strip() or None
        category = (r.get("Category") or "").strip() or None
        guidelines = (r.get("Guidelines") or "").strip() or None

        info(
            f"--- Row {idx}/{len(modified_rows)} --- ID={row_id or 'NA'} | Category={category or 'NA'} | Topic={topic}")

        # Skip if 'Podcast Description' already exists and is non-empty
        if r.get('Podcast Description', '').strip():
            info("Skipping generation for this row: 'Podcast Description' already exists.")
            continue

        try:
            _, _, podcast_description = await process_row(
                client=client,
                topic=topic,
                subtopics=subtopics,
                guidelines=guidelines,
                target_wc=target_wc,
                outdir=outdir,
                schema_hint=compact_schema_hint,
                script_instructions=script_instructions,
                row_id=row_id,
                category=category,
                max_concurrency=max_concurrency,
                verbose=not quiet,
            )
            # XXXX Need to break the loop if process_row encounters an empty section somehow
            # Update the row dictionary with the new description
            print("Podcast description to be saved: " + podcast_description)
            modified_rows[idx - 1]['Podcast Description'] = podcast_description

        except Exception as e:
            err(f"Topic '{topic}' failed: {e}")
            # Continue to next topic

    # Write all rows (including updated and unchanged) back to the original CSV
    write_csv(csv_path, modified_rows, fieldnames)


def main():
    parser = argparse.ArgumentParser(description="Async Gemini pipeline: reports + audio scripts (Free Tier friendly).")
    parser.add_argument("--csv", required=True,
                        help="CSV path (Topic, Target Character Count[, Sub-topics, ID, Category, Guidelines, Podcast Description])")
    parser.add_argument("--outdir", required=True, help="Output directory")
    # parser.add_argument("--report_prose_sample", default="", help="Sample of text prose to guide report style")
    parser.add_argument("--script_instructions", required=True, help="Path to script instructions prompt text")
    parser.add_argument("--outline_schema_hint", required=True, help="Path to outline JSON example or schema hint")
    parser.add_argument("--max_concurrency", type=int, default=3, help="Max parallel section generations per topic")
    parser.add_argument("--no_preview", action="store_true", help="Skip CSV preview (pandas)")
    parser.add_argument("--quiet", action="store_true", help="Less verbose logging")
    args = parser.parse_args()

    asyncio.run(run_all(
        csv_path=args.csv,
        outdir=args.outdir,
        model=args.model,
        # report_prose_sample_path = args.report_prose_sample,
        script_instructions_path=args.script_instructions,
        outline_schema_hint_path=args.outline_schema_hint,
        max_concurrency=args.max_concurrency,
        quiet=args.quiet,
        no_preview=args.no_preview,
    ))


if __name__ == "__main__":
    main()