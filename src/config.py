"""All project settings in one place (same idea as the solution kit's config.py).
Secrets come from your private .env file; everything else can be tuned here.
"""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent      # the project folder
load_dotenv(ROOT / ".env")

# ---- Folders
DATA_DIR = ROOT / "data"                # 4 tables (looked up directly, not searched)
DOCS_DIR = ROOT / "docs"                # 29 policy documents  -> RAG
TRANSCRIPTS_DIR = ROOT / "transcripts"  # 12 meeting transcripts -> RAG (per account)
EVAL_DIR = ROOT / "eval"
INDEX_DIR = ROOT / "index"              # local copy of the chunks, used for BM25 keyword search

# ---- "Today" is fixed so dates line up with the data and the test answers
TODAY = date.fromisoformat(os.getenv("TODAY", "2026-10-17"))

# ---- The brain: Nebius (or any OpenAI-compatible provider)
LLM_API_KEY = os.getenv("NEBIUS_API_KEY")
LLM_BASE_URL = os.getenv("NEBIUS_BASE_URL")
CHAT_MODEL = os.getenv("CHAT_MODEL")
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "")   # optional: low / medium / high (gpt-oss models)

# ---- The memory: Pinecone
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "cloudpaw-renewals")

# ---- The translator: free embedding model that runs on your laptop
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384                         # Pinecone index must be created with this dimension

# ---- Namespaces = separate sections inside one Pinecone index
OU_NAMESPACES = {"GLOBAL": "global", "AMER": "amer", "EMEA": "emea",
                 "South Asia": "south-asia", "LATAM": "latam", "ANZ": "anz"}
TRANSCRIPT_NAMESPACE = "transcripts"

# ---- Chunking (Session 1, Level 7)
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# ---- Retrieval knobs (used from Step 4)
TOP_K = 5              # chunks per search, per method
RRF_K = 60             # Reciprocal Rank Fusion constant
MAX_RETRIES = 2        # retry cap for the grader/checker loops (like the solution kit)
