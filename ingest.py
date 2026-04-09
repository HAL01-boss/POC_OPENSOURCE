import os
import time
from dotenv import load_dotenv
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
import qdrant_client

load_dotenv()

# --- Configuration ---
DOSSIER_ACENOS = r"C:\Users\HoudaALOUANE\ACENOS"  # ← adapte si besoin
EXTENSIONS_AUTORISEES = [".pdf", ".docx", ".pptx", ".txt", ".xlsx"]
BATCH_SIZE = 100       # chunks par batch (local = pas de rate limit)
PAUSE_SECONDES = 2     # petite pause pour ne pas saturer la RAM

# --- Embeddings HuggingFace (local, gratuit, excellent pour le français) ---
# Le modèle se télécharge automatiquement au premier lancement (~1.2 Go)
print("⬇️  Chargement du modèle d'embedding (premier lancement : ~1.2 Go)...")
Settings.embed_model = HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-large",
    max_length=512,
)
Settings.chunk_size = 512
Settings.chunk_overlap = 64

# --- Connexion Qdrant ---
client = qdrant_client.QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)
vector_store = QdrantVectorStore(client=client, collection_name="acenos_kb")
storage_context = StorageContext.from_defaults(vector_store=vector_store)

# --- Chargement récursif de tous les fichiers ---
print(f"\n📂 Scan du dossier : {DOSSIER_ACENOS}")
documents = SimpleDirectoryReader(
    input_dir=DOSSIER_ACENOS,
    recursive=True,
    required_exts=EXTENSIONS_AUTORISEES,
    filename_as_id=True,
    errors="ignore",
).load_data()

total = len(documents)
print(f"✅ {total} chunks chargés")
print(f"🔄 Indexation par batches de {BATCH_SIZE}...\n")

# --- Indexation par batches avec retry automatique ---
for i in range(0, total, BATCH_SIZE):
    batch = documents[i:i + BATCH_SIZE]
    debut = i + 1
    fin = min(i + BATCH_SIZE, total)

    try:
        VectorStoreIndex.from_documents(
            batch,
            storage_context=storage_context,
        )
        print(f"  ✅ Batch {debut}-{fin} / {total} indexé")
    except Exception as e:
        print(f"  ⚠️  Erreur batch {debut}-{fin} : {e}")
        print(f"  ⏳ Pause 30s avant de réessayer...")
        time.sleep(30)
        try:
            VectorStoreIndex.from_documents(batch, storage_context=storage_context)
            print(f"  ✅ Batch {debut}-{fin} réessayé avec succès")
        except Exception as e2:
            print(f"  ❌ Batch {debut}-{fin} échoué définitivement : {e2}")

    if fin < total:
        time.sleep(PAUSE_SECONDES)

print(f"\n🎉 Indexation terminée ! {total} chunks dans Qdrant.")