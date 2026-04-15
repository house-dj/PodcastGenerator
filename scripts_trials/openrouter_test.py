import os
import requests
import requests.exceptions
import json
from openrouter import OpenRouter


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
print(OPENROUTER_API_KEY)
# REWRITE_MODEL = "gemini-2.5-flash"
MAX_LLM_REWRITES = 2 # Only one rewrite attempt allowed
REWRITE_SYSTEM_PROMPT = (
    "You are an expert text cleanser and audio script writer. Your task is to minimally "
    "rewrite a short passage of text that has repeatedly failed a Text-to-Speech (TTS) API. "
    "The failure is likely due to long sentences, invisible characters, complex punctuation, or unusual phrasing/tags. "
    "Rewrite the text to be 20% shorter and compatible with a strict TTS engine. "
    "Maintain the original meaning and structure, but eliminate any potential complexity. "
    "Use shorter sentences up to 20 words long."
    "Maintain SSML tags as-is. "
    "Use spoken format ('eighteen forty-two') for years. Render monarchs as 'the Second', 'the Third'."
    "DO NOT ADD NEW LINES or HTML or new SSML. Output ONLY the clean, rewritten text."
)
failed_chunk = "The Olmec elite likely legitimized power through connection to sacred forces, presiding over elaborate rituals and managing a stratified society that supported artisans, priests, and laborers. Early calendrical concepts and a precursor to later Mesoamerican writing systems are also attributed to the Olmec, suggesting intellectual advancements crucial for the region's history.Olmec influence extended far beyond their Gulf Coast heartland, disseminated through extensive trade networks exchanging goods like obsidian, jade, iron ore, and specialized ceramics."
chunk_index = 1
if not OPENROUTER_API_KEY:
    print("🛑 Error: OPENROUTER_API_KEY environment variable not set. Cannot rewrite chunk.")
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
    print(response.choices[0].message.content)
    print(response.model)
except Exception as e:
    print(f"An error occurred: {e}")

"""
try:
    response = requests.post(
      url="https://openrouter.ai/api/v1/chat/completions",
      headers={
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
          'Content-Type': 'application/json'
        # "HTTP-Referer": "<YOUR_SITE_URL>", # Optional. Site URL for rankings on openrouter.ai.
        # "X-Title": "<YOUR_SITE_NAME>", # Optional. Site title for rankings on openrouter.ai.
      },
      data=json.dumps({
        # "model": "openai/gpt-4o", # Optional
        "messages": [
            {
            "role": "system",
            "content": REWRITE_SYSTEM_PROMPT
            },
            {
            "role": "user",
            "content": user_prompt
            }
        ]
      })
    )

    print(response)
    #text = response.output_text
    #text = response.choices[0].message.content
    #if not text:
     #   print(f"🛑 Error: LLM returned empty text for chunk {chunk_index + 1}.")
    #print(text)
except requests.exceptions.HTTPError as e:
    print(f" OpenRouter HTTP Error: {e.response.status_code} - {e.response.text}")
except requests.exceptions.ConnectionError as e:
    print(f"OpenRouter Connection Error: {e}")
except requests.exceptions.Timeout as e:
    print(f"OpenRouter Timeout Error: {e}")
except requests.exceptions.RequestException as e:
    print(f"OpenRouter - An unexpected Request Error occurred: {e}")
except KeyError:
    print("OpenRouter Error: Unexpected response format from OpenRouter API.")
"""

