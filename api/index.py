import os
import sys

# Vercel runs this file from api/ — add project root so app + mailing import work.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app  # noqa: E402, F401
