#!/usr/bin/env python3
import sys
from pathlib import Path

from fastmcp import FastMCP

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common

# Inicializa servidor MCP
mcp = FastMCP("knowledge")

# Verifica dependências opcionais (RAG)
try:
    import chromadb
    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError:
        from langchain_community.embeddings import OllamaEmbeddings
    HAS_RAG_DEPS = True
except ImportError:
    HAS_RAG_DEPS = False

@mcp.tool(name="access_knowledge")
def access_knowledge(query: str, n_results: int = 3) -> str:
    """
    Consulta a Base de Conhecimento (RAG) para obter informações sobre regras, padrões e documentação do projeto.
    Use isso quando o usuário fizer perguntas sobre 'como fazer', 'regras', 'padrões', 'arquitetura' ou 'decisões'.

    Args:
        query: A pergunta ou termo de busca (ex: "como criar bucket s3", "regras de tag").
        n_results: Número de resultados para retornar (padrão 3).
    """
    if not HAS_RAG_DEPS:
        return "⛔ Erro: Dependências de RAG não instaladas. O administrador deve executar 'pip install chromadb langchain-community'."

    try:
        # Conecta ao ChromaDB (Docker)
        client = chromadb.HttpClient(host='localhost', port=8000)
        try:
            client.heartbeat()
        except Exception:
            return "⛔ Erro: Não foi possível conectar ao ChromaDB (Porta 8000). Verifique se o container 'aponte_vector_db' está rodando."

        # Configura Embedding (Ollama) - Deve bater com o usado na ingestão
        embedding_model = OllamaEmbeddings(
            model="nomic-embed-text", 
            base_url="http://127.0.0.1:11434"
        )
        
        # Obtém coleção
        try:
            collection = client.get_collection(name="aponte_knowledge")
        except Exception:
            return "⚠️ A base de conhecimento está vazia ou não foi inicializada. Execute o script de ingestão 'core/services/knowledge/ingestor.py' primeiro."

        # Gera embedding da query
        query_embedding = embedding_model.embed_query(query)
        
        # Consulta
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        
        if not results['documents'] or not results['documents'][0]:
            return "Nenhuma informação relevante encontrada na base de conhecimento."

        formatted_results = []
        for i, doc in enumerate(results['documents'][0]):
            meta = results['metadatas'][0][i] if results['metadatas'] and results['metadatas'][0] else {}
            source = meta.get('source', 'unknown')
            formatted_results.append(f"--- Fonte: {source} ---\n{doc}\n")
            
        return "\n".join(formatted_results)

    except Exception as e:
        return f"⛔ Erro ao consultar conhecimento: {str(e)}"

if __name__ == "__main__":
    mcp.run()