"""
Servidor MCP de Pesquisa (Research Agent).
Expõe capacidades de navegação web e busca para o Cérebro da IA.

Este servidor atua como uma ponte entre o LLM (Cerebro-AI) e o mundo externo,
usando o Crawl4AI para leitura profunda e DuckDuckGo para descoberta.
"""

import json
import os
import re
from pathlib import Path

# Dependências: pip install fastmcp duckduckgo-search requests
try:
    from fastmcp import FastMCP
except ImportError:
    raise ImportError("FastMCP não instalado. Execute: pip install fastmcp")

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

import requests

# Tenta importar BeautifulSoup para limpeza de HTML (Fallback Mode)
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from core.lib.mcp_utils import handle_mcp_errors

# Configuração: Aponta para o container Docker do Crawl4AI
CRAWLER_API_URL = os.getenv("CRAWL4AI_API_URL", "http://localhost:11235/crawl")

# --- GUARDRAILS DE SEGURANÇA (FREIOS) ---
# Termos proibidos para garantir o uso ético e corporativo da ferramenta.
BLOCKED_TERMS = [
    "hackear",
    "invadir",
    "quebrar senha",
    "roubar senha",
    "bypass auth",
    "crackear",
    "warez",
    "torrent",
    "porn",
    "xxx",
    "darkweb",
    "onion",
    "how to hack",
    "password cracker",
    "exploit kit",
    "keylogger",
]


def validate_safety(text: str) -> bool:
    """Verifica se o texto contém termos proibidos (Blacklist)."""
    text_lower = text.lower()
    for term in BLOCKED_TERMS:
        if term in text_lower:
            return False
    return True


# Inicializa o servidor FastMCP
mcp = FastMCP("Research Agent")


def _clean_html_fallback(html_content: str) -> str:
    """Limpa HTML para texto puro quando o Crawl4AI está indisponível."""
    bs4_error = None
    if BeautifulSoup:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            # Remove scripts e estilos
            for element in soup(["script", "style", "meta", "noscript", "header", "footer", "nav"]):
                element.extract()
            # Extrai texto
            text = soup.get_text(separator="\n")
            # Remove linhas vazias excessivas
            lines = (line.strip() for line in text.splitlines())
            return "\n".join(chunk for chunk in lines if chunk)
        except Exception as e:
            bs4_error = str(e)
            pass

    # Fallback Regex (Pior qualidade, mas funciona)
    text = re.sub(r"<(script|style).*?>.*?</\1>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if bs4_error:
        text = f"[Aviso: BeautifulSoup falhou ({bs4_error}), limpeza via Regex]\n{text}"

    return text

@mcp.tool(name="web_search")
@handle_mcp_errors
def web_search(query: str, max_results: int = 5, project_name: str = None, environment: str = None) -> list:
    """
    Pesquisa na web por tópicos técnicos, documentação ou soluções de erros.
    Retorna uma lista JSON com título, link e resumo.
    Use isso quando não souber uma resposta ou precisar de dados atualizados.

    Examples:
        query='terraform aws s3 bucket versioning error'
    """
    if not validate_safety(query):
        return [{"title": "Erro", "body": "⛔ Busca Bloqueada: Termos proibidos."}]

    if not DDGS:
        return [{"title": "Erro", "body": "Biblioteca duckduckgo-search não instalada."}]

    results = []
    try:
        with DDGS() as ddgs:
            # backend='html' é mais lento mas mais estável contra rate limits
            ddgs_gen = ddgs.text(query, max_results=max_results, backend="html")
            for r in ddgs_gen:
                results.append(r)
    except Exception as e:
        return [{"title": "Erro", "body": f"Falha na busca: {e}"}]

    return results


@mcp.tool(name="read_url")
@handle_mcp_errors
def read_url(url: str, project_name: str = None, environment: str = None) -> str:
    """
    Lê o conteúdo de uma URL específica para aprendizado profundo.
    Usa o Crawl4AI (se disponível) para renderizar JS e limpar o HTML.

    Examples:
        url='https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket'
    """
    if not validate_safety(url):
        return "⛔ Acesso Bloqueado: A URL contém termos suspeitos."

    crawler_error = None
    # 1. Tenta via Crawl4AI (Container) para melhor qualidade
    try:
        response = requests.post(
            CRAWLER_API_URL, json={"urls": url, "priority": 10}, timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            # O Crawl4AI retorna uma lista de resultados
            results = data.get("results", [])
            if results:
                content = results[0].get("markdown", "")
                if content:
                    # Trunca para evitar estourar o contexto da IA (Safety Cap)
                    return f"--- Conteúdo de {url} ---\n{content[:15000]}"
    except Exception as e:
        crawler_error = str(e)

    # 2. Fallback simples (Requests) caso o container esteja offline
    try:
        res = requests.get(
            url, timeout=10, headers={"User-Agent": "A-PONTE-Research/1.0"}
        )
        clean_text = _clean_html_fallback(res.text)

        header = f"--- Conteúdo (Lite Mode) de {url} ---\n"
        if crawler_error:
             header += f"[Aviso: Crawler Avançado indisponível ({crawler_error}). Usando modo básico.]\n"

        return f"{header}{clean_text[:8000]}"
    except Exception as e:
        return f"Erro ao ler URL: {e} (Crawler error: {crawler_error})"


@mcp.resource("knowledge://sources")
def get_sources_list() -> str:
    """Lê a lista atual de fontes de aprendizado (docs/sources.txt)."""
    path = Path("docs/sources.txt")
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "# Arquivo não encontrado"


if __name__ == "__main__":
    # Permite execução direta para teste ou via MCP Client
    mcp.run()
