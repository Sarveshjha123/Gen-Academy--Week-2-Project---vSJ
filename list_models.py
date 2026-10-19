"""List the chat models your Nebius key can use (no secrets printed)."""
import os
from dotenv import load_dotenv
from openai import OpenAI
load_dotenv()
client = OpenAI(api_key=os.getenv("NEBIUS_API_KEY"), base_url=os.getenv("NEBIUS_BASE_URL"))
for m in sorted(client.models.list(), key=lambda m: m.id):
    print(m.id)
