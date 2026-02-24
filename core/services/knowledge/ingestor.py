#!/usr/bin/env python3
"""
RAG Ingestor (O Bibliotecário)
------------------------------
Lê documentação local (ADRs, Manuais) e indexa no ChromaDB para consulta semântica.
"""

import os
import sys
import uuid
from pathlib import Path
from typing import List, Dict
import requests

# Setup paths
project_root = Path(__file__).parents[3].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common
from core.services import llm_gateway

# Tenta importar dependências RAG (Graceful degradation)
try:
    import chromadb
    from chromadb.config import Settings
    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError:
        from langchain_community.embeddings import OllamaEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    HAS_RAG_DEPS = True
except ImportError:
    HAS_RAG_DEPS = False


class KnowledgeIngestor:
    def __init__(self):
        if not HAS_RAG_DEPS:
            common.console.print("[red]❌ Dependências RAG não encontradas. Execute: pip install chromadb langchain-community langchain-text-splitters[/red]")
            sys.exit(1)

        try:
            self.chroma_client = chromadb.HttpClient(host='localhost', port=8000)
            self.chroma_client.heartbeat()
        except Exception:
            common.console.print("[bold red]❌ Erro: Não foi possível conectar ao ChromaDB (Porta 8000).[/bold red]")
            common.console.print("👉 Certifique-se de que o container está rodando:\n   [cyan]docker compose -f config/containers/docker-compose.yml up -d vector-db[/cyan]")
            sys.exit(1)

        # Check Ollama connection
        if not llm_gateway.is_available():
            common.console.print("[yellow]⏳ Ollama não detectado. Tentando iniciar automaticamente...[/yellow]")
            if not llm_gateway.start_server():
                common.console.print("[bold red]❌ Erro: Não foi possível iniciar o Ollama.[/bold red]")
                sys.exit(1)

        # Usa modelo leve para embeddings (nomic-embed-text é o padrão ouro para RAG local)
        self.embedding_model = OllamaEmbeddings(model="nomic-embed-text", base_url="http://127.0.0.1:11434")

        # Coleção principal
        self.collection = self.chroma_client.get_or_create_collection(name="aponte_knowledge")

        # Splitter otimizado para Markdown
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=600,
            chunk_overlap=100,
            separators=["\n## ", "\n### ", "\n", " ", ""]
        )

    def scan_docs(self) -> List[Dict]:
        """Varre diretórios de documentação em busca de arquivos Markdown."""
        root = common.get_project_root()
        docs = []

        scan_paths = [
            root / "docs" / "adrs",
            root / "docs" / "manuals",
            root / "docs" / "knowledge_base",
            root / ".aponte" / "chat_sessions"
        ]

        # Adiciona arquivos raiz importantes
        single_files = ["MANIFESTO.md", "SECURITY.md", "TROUBLESHOOTING.md"]
        for f in single_files:
            path = root / "docs" / f
            if path.exists():
                docs.append(path)

        for p in scan_paths:
            if p.exists():
                docs.extend(list(p.glob("*.md")))

        return docs

    def process_file(self, file_path: Path):
        """Lê, divide e indexa um arquivo."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                return

            chunks = self.splitter.create_documents([content])

            ids = []
            documents = []
            metadatas = []

            common.console.print(f"[dim]📄 Processando {file_path.name} ({len(chunks)} chunks)...[/dim]")

            for i, chunk in enumerate(chunks):
                chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{file_path.name}_{i}"))
                ids.append(chunk_id)
                documents.append(chunk.page_content)
                metadatas.append({
                    "source": str(file_path.name),
                    "path": str(file_path),
                    "type": "documentation"
                })

            # Gera embeddings e salva (OllamaEmbeddings faz a chamada ao Ollama aqui)
            # Nota: ChromaDB com HttpClient não aceita função de embedding direta facilmente na versão atual,
            # então geramos os embeddings manualmente ou deixamos o Chroma server gerar se configurado.
            # Para simplicidade e controle local, vamos gerar aqui.
            embeddings = self.embedding_model.embed_documents(documents)

            self.collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )

        except Exception as e:
            common.console.print(f"[yellow]⚠️  Falha ao processar {file_path.name}: {e}[/yellow]")

    def run(self):
        common.console.rule("[bold magenta]🧠 RAG Ingestor[/]")
        docs = self.scan_docs()
        common.console.print(f"[bold]Encontrados {len(docs)} documentos para indexação.[/bold]")

        for doc in docs:
            self.process_file(doc)

        common.console.print(f"[bold green]✅ Ingestão concluída! {self.collection.count()} vetores na base.[/bold green]")

if __name__ == "__main__":
    ingestor = KnowledgeIngestor()
    ingestor.run()