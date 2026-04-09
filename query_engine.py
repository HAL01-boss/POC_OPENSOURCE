import os
from dotenv import load_dotenv
from llama_index.core import VectorStoreIndex, StorageContext, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.anthropic import Anthropic
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.postprocessor import SentenceTransformerRerank
import qdrant_client
import streamlit as st

# --- Chargement des variables d'environnement ---
load_dotenv()

try:
    if hasattr(st, "secrets") and len(st.secrets) > 0:
        for key, value in st.secrets.items():
            os.environ[key] = value
except Exception:
    pass

# --- Chargement du prompt système ---
prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
with open(prompt_path, "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

# --- Embeddings HuggingFace (local, gratuit) ---
Settings.embed_model = HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-large",
    max_length=512,
)

# --- LLM Claude Sonnet ---
Settings.llm = Anthropic(
    model="claude-sonnet-4-5",
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

# --- Connexion Qdrant ---
client = qdrant_client.QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)

# Vérification que la collection existe
collections = client.get_collections().collections
noms = [c.name for c in collections]
if "acenos_kb" not in noms:
    raise Exception(
        "La collection 'acenos_kb' n'existe pas dans Qdrant. "
        "Lance d'abord ingest.py pour indexer tes documents."
    )

vector_store = QdrantVectorStore(client=client, collection_name="acenos_kb")
storage_context = StorageContext.from_defaults(vector_store=vector_store)
index = VectorStoreIndex.from_vector_store(
    vector_store,
    storage_context=storage_context
)

# --- Reranker ZeroEntropy zerank-1-small (gratuit, open source) ---
reranker = SentenceTransformerRerank(
    model="zeroentropy/zerank-1-small",
    top_n=5,
)


def get_query_engine():
    """Retourne le moteur de requête RAG avec reranking."""
    return index.as_query_engine(
        similarity_top_k=10,
        node_postprocessors=[reranker],
        system_prompt=SYSTEM_PROMPT,
        response_mode="compact",
    )


def format_sources(response) -> str:
    """Formate les sources avec fichier, page, score et extrait."""
    sources = []
    seen = set()

    for i, node in enumerate(response.source_nodes):
        meta = node.metadata
        fichier = meta.get("file_name", meta.get("filename", "Document inconnu"))
        page = meta.get("page_label", meta.get("page_number", None))
        section = meta.get("section", meta.get("header", None))
        score = node.score if node.score is not None else 0.0
        extrait = node.text[:250].replace("\n", " ").strip()
        if len(node.text) > 250:
            extrait += "..."

        cle = f"{fichier}-{page}"
        if cle in seen:
            continue
        seen.add(cle)

        ligne = f"**[{i+1}] {fichier}**\n"
        if page:
            ligne += f"  • 📄 Page : {page}\n"
        if section:
            ligne += f"  • 📌 Section : {section}\n"
        ligne += f"  • 🎯 Pertinence : {score:.0%}\n"
        ligne += f"  • 💬 Extrait : *\"{extrait}\"*"
        sources.append(ligne)

    if not sources:
        return "⚠️ Aucune source trouvée dans la base de connaissances."

    return "\n\n---\n\n".join(sources)


# --- Test rapide en terminal ---
if __name__ == "__main__":
    engine = get_query_engine()
    question = input("Ta question : ")
    response = engine.query(question)
    print("\n=== RÉPONSE ===\n")
    print(response)
    print("\n=== SOURCES ===\n")
    print(format_sources(response))