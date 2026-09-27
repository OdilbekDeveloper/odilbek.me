"""Load a local .env file, for development and tests only.

dev.py and test.py call this before importing base.py, which reads the environment at import time.
prod.py never does: production takes its configuration from the real environment alone, so a
stray .env can never feed it values. Variables already set in the environment always win.
"""

from pathlib import Path

import environ

DOTENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


def load_dotenv():
    if DOTENV_PATH.is_file():
        environ.Env.read_env(DOTENV_PATH)
