"""Step 3 · OFFLINE INGEST: load → chunk → embed → store in Pinecone (+ save chunks for BM25).
Run from the project folder:   python -m src.ingest
"""
import json
import time

import yaml
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from pinecone import Pinecone, ServerlessSpec

from src import config


# ----------------------------------------------------------------------------- 1. LOAD
def load_markdown_folder(folder):
    """Read every .md file. The block between the --- lines at the top becomes METADATA."""
    docs = []
    for path in sorted(folder.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        _, front_matter, body = raw.split("---", 2)
        meta = {k: str(v) for k, v in (yaml.safe_load(front_matter) or {}).items()}
        # 2. CLEAN: drop the "fictional data" banner line, it's not useful for answers
        body = "\n".join(l for l in body.splitlines() if not l.startswith("> Fictional data"))
        docs.append(Document(page_content=body.strip(), metadata=meta))
    return docs


# ----------------------------------------------------------------------------- 3. CHUNK
def chunk(docs):
    """Split by headings first (one rule or promotion per chunk), then cut long pieces to 800 chars with 100 overlap."""
    by_heading = MarkdownHeaderTextSplitter([("#", "h1"), ("##", "h2")], strip_headers=False)
    by_size = RecursiveCharacterTextSplitter(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP)
    chunks = []
    for doc in docs:
        for s, section in enumerate(by_heading.split_text(doc.page_content)):
            heading = section.metadata.get("h2") or section.metadata.get("h1") or ""
            for p, piece in enumerate(by_size.split_text(section.page_content)):
                meta = dict(doc.metadata)
                meta["heading"] = heading
                meta["chunk_id"] = f"{meta['doc_id']}#{s}.{p}"
                meta["effective_to_int"] = int(meta.get("effective_to", "2099-12-31").replace("-", ""))
                # A small label at the top of each chunk so it "knows" where it came from
                label = f"[{meta['doc_id']} | OU: {meta['ou']} | {meta.get('title', '')} | {heading}]\n"
                chunks.append(Document(page_content=label + piece, metadata=meta))
    return chunks


def namespace_for(chunk_doc):
    if chunk_doc.metadata.get("doc_type") == "meeting_transcript":
        return config.TRANSCRIPT_NAMESPACE
    return config.OU_NAMESPACES[chunk_doc.metadata["ou"]]


# ----------------------------------------------------------------------------- 5. STORE (create the index once)
def get_or_create_index(pc):
    existing = pc.list_indexes().names()
    if config.PINECONE_INDEX not in existing:
        print(f"Creating Pinecone index '{config.PINECONE_INDEX}' (dimension {config.EMBED_DIM}, cosine)...")
        pc.create_index(name=config.PINECONE_INDEX, dimension=config.EMBED_DIM, metric="cosine",
                        spec=ServerlessSpec(cloud="aws", region="us-east-1"))
        while not pc.describe_index(config.PINECONE_INDEX).status["ready"]:
            time.sleep(2)
    return pc.Index(config.PINECONE_INDEX)


def main():
    # 1–2. Load + clean
    policy_docs = load_markdown_folder(config.DOCS_DIR)
    transcripts = load_markdown_folder(config.TRANSCRIPTS_DIR)
    print(f"Loaded {len(policy_docs)} policy documents and {len(transcripts)} meeting transcripts")

    # 3. Chunk
    chunks = chunk(policy_docs + transcripts)
    print(f"Split them into {len(chunks)} chunks")

    # 4. Embed (the model downloads once, then runs on your laptop for free)
    embeddings = HuggingFaceEmbeddings(model_name=config.EMBED_MODEL)

    # 5. Store in Pinecone, one namespace per section
    pc = Pinecone(api_key=config.PINECONE_API_KEY)
    index = get_or_create_index(pc)
    groups = {}
    for c in chunks:
        groups.setdefault(namespace_for(c), []).append(c)
    for ns, items in groups.items():
        try:
            index.delete(delete_all=True, namespace=ns)   # start clean so re-running is safe
        except Exception:
            pass                                           # namespace didn't exist yet: fine
        store = PineconeVectorStore(index=index, embedding=embeddings, namespace=ns)
        store.add_documents(items, ids=[c.metadata["chunk_id"] for c in items])
        print(f"  uploaded {len(items):>3} chunks to namespace '{ns}'")

    # 6. Save the same chunks locally: BM25 keyword search will use them (hybrid search, Step 4)
    config.INDEX_DIR.mkdir(exist_ok=True)
    (config.INDEX_DIR / "chunks.json").write_text(json.dumps(
        [{"text": c.page_content, "metadata": c.metadata} for c in chunks], ensure_ascii=False, indent=1))
    print("Saved index/chunks.json for keyword (BM25) search")

    time.sleep(5)  # Pinecone takes a few seconds to count new vectors
    stats = index.describe_index_stats().to_dict()
    print(f"\nPinecone now holds {stats['total_vector_count']} chunks (may lag a few seconds behind):")
    for ns, info in sorted(stats["namespaces"].items()):
        print(f"  {ns:<12} {info['vector_count']}")

    # Peek at one stored chunk so you can see what "a chunk + its metadata" looks like
    sample = next(c for c in chunks if c.metadata["doc_id"] == "EMEA-REN-201" and "Notice" in c.metadata["heading"])
    print("\nExample chunk:\n", sample.page_content)
    print("Its metadata:", {k: sample.metadata[k] for k in ("doc_id", "ou", "doc_type", "heading", "chunk_id")})


if __name__ == "__main__":
    main()
