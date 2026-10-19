"""Step 1 check: can this laptop reach Nebius, Pinecone, and run the free embedding model?
Run:  python test_connection.py
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads your private .env file

# 1) Nebius: send one tiny message to the LLM
try:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=os.getenv("CHAT_MODEL"), api_key=os.getenv("NEBIUS_API_KEY"),
                     base_url=os.getenv("NEBIUS_BASE_URL"), temperature=0)
    reply = llm.invoke("Reply with exactly one word: OK").content
    print("✅ Nebius works. The model replied:", reply.strip()[:40])
except Exception as e:
    print("❌ Nebius failed:", str(e)[:300])

# 2) Pinecone: log in and list your indexes
try:
    from pinecone import Pinecone
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    names = [i["name"] for i in pc.list_indexes()]
    print("✅ Pinecone works. Your indexes:", names or "(none yet, that's fine)")
except Exception as e:
    print("❌ Pinecone failed:", str(e)[:300])

# 3) Embeddings: turn a sentence into numbers on your own laptop (first run downloads ~90 MB)
try:
    from langchain_huggingface import HuggingFaceEmbeddings
    emb = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vec = emb.embed_query("Refunds are processed within 14 days")
    print(f"✅ Embeddings work. One sentence became {len(vec)} numbers, starting {[round(v, 3) for v in vec[:3]]}")
except Exception as e:
    print("❌ Embeddings failed:", str(e)[:300])
