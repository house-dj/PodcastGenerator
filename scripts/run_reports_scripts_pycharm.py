# run_reports_scripts_pycharm.py
"""
Simple PyCharm runner for generate_reports_and_scripts_async.py

Usage:
- Edit the CONFIG values below (paths, model, concurrency).
- Ensure GEMINI_API_KEY is set in your environment (PyCharm > Run/Debug Config > Environment).
- Run this file in PyCharm.

Two modes:
  1) run_via_run_all(): calls the async pipeline function directly (recommended).
  2) run_via_main(): simulates CLI args & calls main() (if you prefer the CLI flow).

Pick the mode at the bottom by toggling which function is called in __main__.
"""

import os
import sys
import asyncio
from pathlib import Path

# --- Adjust these for your environment ---
PODCAST_GENERATOR_DIR = os.path.join(os.getenv('PODCAST_GENERATOR_DIR'))
topics_path = os.path.join(PODCAST_GENERATOR_DIR,'/inputs/topics.csv')
output_text_path = os.path.join(PODCAST_GENERATOR_DIR,"./text generation files/generated_text_files")
CONFIG = {
    # CSV with columns: Topic, TargetWordCount[, Sub-topics]
    "csv": topics_path.resolve(),
    # Output directory for generated files
    "outdir": output_text_path.resolve(),
    # Model: for free tier limiter in your script, you likely set gemini-2.5-flash
    "model": "gemini-2.5-flash",
    # Parallelism per topic (matches your async script)
    "max_concurrency": 3,
    # Optional toggles
    "no_preview": True,
    "quiet": False,
}

# Optional: load a local .env if you like
# (Uncomment if you have python-dotenv installed)
# from dotenv import load_dotenv
# load_dotenv()

# Sanity check so PyCharm surfaces a helpful error early
if not os.getenv("OPENROUTER_API_KEY"):
    raise SystemExit(
        "OPENROUTER_API_KEY is not set. Configure it in PyCharm: "
        "Run/Debug Configurations > Environment variables."
    )

# Make sure we can import the main module
HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))

# Import your async pipeline and CLI main
from generate_reports_and_scripts_async import run_all as pipeline_run_all  # type: ignore
from generate_reports_and_scripts_async import main as pipeline_main       # type: ignore


async def run_via_run_all() -> None:
    """Preferred: call the async function directly (no CLI parsing)."""
    await pipeline_run_all(
        csv_path=CONFIG["csv"],
        outdir=CONFIG["outdir"],
        max_concurrency=CONFIG["max_concurrency"],
        quiet=CONFIG["quiet"],
        no_preview=CONFIG["no_preview"],
    )


def run_via_main() -> None:
    """
    Alternate: simulate CLI args then call the script's main().
    Useful if you want exactly the CLI behavior from inside PyCharm.
    """
    argv = [
        "generate_reports_and_scripts_async.py",
        "--csv", CONFIG["csv"],
        "--outdir", CONFIG["outdir"],
        "--max_concurrency", str(CONFIG["max_concurrency"]),
    ]
    if CONFIG["no_preview"]:
        argv.append("--no_preview")
    if CONFIG["quiet"]:
        argv.append("--quiet")

    # Temporarily replace sys.argv
    old_argv = sys.argv[:]
    try:
        sys.argv = argv
        pipeline_main()
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    # Choose ONE mode to run.
    # 1) Direct async (recommended):
    asyncio.run(run_via_run_all())

    # 2) Or: CLI-style main():
    # run_via_main()
