"""Step 4 · HYBRID SEARCH = meaning (Pinecone) + keywords (BM25), merged with Reciprocal Rank Fusion.
Try it:   python -m src.retriever
"""
import json
import math
import re
from collections import Counter
from functools import lru_cache

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone

from src import config

TODAY_INT = int(config.TODAY.strftime("%Y%m%d"))


# ----------------------------------------------------------------------------- the searchable "sections"
def sections_for(ou=None, account_id=None):
    """Which namespaces to search. Region rules + global rules + (optionally) one customer's meetings."""
    if ou:
        names = [config.OU_NAMESPACES[ou], config.OU_NAMESPACES["GLOBAL"]]
    else:
        names = list(config.OU_NAMESPACES.values())       # no region known: search all policy sections
    if account_id:
        names.append(config.TRANSCRIPT_NAMESPACE)
    return names


def allowed(meta, namespaces, account_id):
    """Same rules as the Pinecone filters, applied to the local chunks for BM25."""
    if meta.get("doc_type") == "meeting_transcript":
        return config.TRANSCRIPT_NAMESPACE in namespaces and meta.get("account_id") == account_id
    ns = config.OU_NAMESPACES[meta["ou"]]
    return ns in namespaces and int(meta["effective_to_int"]) >= TODAY_INT


# ----------------------------------------------------------------------------- 1. MEANING (dense, Pinecone)
@lru_cache(maxsize=1)
def _store():
    embeddings = HuggingFaceEmbeddings(model_name=config.EMBED_MODEL)
    index = Pinecone(api_key=config.PINECONE_API_KEY).Index(config.PINECONE_INDEX)
    return PineconeVectorStore(index=index, embedding=embeddings)


def dense_search(question, namespaces, account_id=None, k=config.TOP_K):
    results = []
    for ns in namespaces:
        if ns == config.TRANSCRIPT_NAMESPACE:
            flt = {"account_id": {"$eq": account_id}}          # only THIS customer's meetings
        else:
            flt = {"effective_to_int": {"$gte": TODAY_INT}}     # only documents still valid today
        results += _store().similarity_search_with_score(question, k=k, filter=flt, namespace=ns)
    results.sort(key=lambda pair: pair[1], reverse=True)       # higher cosine score = closer meaning
    return [doc for doc, _ in results[:k]]


# ----------------------------------------------------------------------------- 2. KEYWORDS (sparse, BM25)
def _tokens(text):
    return [t.strip(".") for t in re.findall(r"[a-z0-9$%.\-]+", text.lower()) if t.strip(".")]


class BM25:
    """Keyword scoring from Session 1: term frequency (with saturation), rarity (IDF), length normalization."""

    def __init__(self, texts, k1=1.2, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [_tokens(t) for t in texts]
        self.avg_len = sum(map(len, self.docs)) / len(self.docs)
        doc_freq = Counter(word for d in self.docs for word in set(d))
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in doc_freq.items()}
        self.tf = [Counter(d) for d in self.docs]

    def score(self, question, i):
        tf, length, s = self.tf[i], len(self.docs[i]), 0.0
        for w in _tokens(question):
            if w in tf:
                s += self.idf[w] * tf[w] * (self.k1 + 1) / (tf[w] + self.k1 * (1 - self.b + self.b * length / self.avg_len))
        return s


@lru_cache(maxsize=1)
def _keyword_index():
    data = json.loads((config.INDEX_DIR / "chunks.json").read_text(encoding="utf-8"))
    chunks = [Document(page_content=d["text"], metadata=d["metadata"]) for d in data]
    return chunks, BM25([c.page_content for c in chunks])


def keyword_search(question, namespaces, account_id=None, k=config.TOP_K):
    chunks, bm25 = _keyword_index()
    scored = [(bm25.score(question, i), c) for i, c in enumerate(chunks) if allowed(c.metadata, namespaces, account_id)]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k]]


# ----------------------------------------------------------------------------- 3. MERGE (Reciprocal Rank Fusion)
def hybrid_search(question, ou=None, account_id=None, k=config.TOP_K):
    namespaces = sections_for(ou, account_id)
    dense = dense_search(question, namespaces, account_id, k)
    sparse = keyword_search(question, namespaces, account_id, k)
    points, by_id = Counter(), {}
    for ranked_list in (dense, sparse):
        for rank, doc in enumerate(ranked_list, start=1):
            cid = doc.metadata["chunk_id"]
            points[cid] += 1 / (config.RRF_K + rank)            # score = sum of 1 / (60 + rank)
            by_id[cid] = doc
    return [by_id[cid] for cid, _ in points.most_common(k)]


# ----------------------------------------------------------------------------- demo
if __name__ == "__main__":
    def show(title, docs):
        print(f"  {title}")
        for i, d in enumerate(docs, 1):
            print(f"     {i}. {d.metadata['chunk_id']:<26} {d.metadata.get('heading', '')[:45]}")

    demos = [
        ("A keyword question (exact code)", "Is promo code AMER-AIA30 stackable?", "AMER", None),
        ("A meaning question (different words)", "How long before the contract ends must we warn a German customer about a price rise?", "EMEA", None),
        ("A customer's own words (transcripts)", "What did the customer say about surprise bills?", "EMEA", "ACC-013"),
    ]
    for label, q, ou, acc in demos:
        ns = sections_for(ou, acc)
        print(f"\n=== {label}\nQ: {q}\n   searching: {ns}")
        show("MEANING (Pinecone):", dense_search(q, ns, acc))
        show("KEYWORDS (BM25):", keyword_search(q, ns, acc))
        show("HYBRID (RRF merged):", hybrid_search(q, ou, acc))
