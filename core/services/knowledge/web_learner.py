#!/usr/bin/env python3
import os
import re
from datetime import datetime
from pathlib import Path

import requests

from core.lib import utils as common

# Tenta importar BeautifulSoup (Padrão da indústria para HTML)
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# Configuração
CRAWLER_API_URL = os.getenv("CRAWL4AI_API_URL", "http://localhost:11235/crawl")


def clean_html(html_content):
    """Limpa HTML para texto puro (Markdown friendly)."""

    # OTIMIZAÇÃO: Usa BeautifulSoup se disponível (Evita "reinventar a roda" com Regex)
    if BeautifulSoup:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            # Remove elementos indesejados
            for element in soup(
                ["script", "style", "meta", "noscript", "header", "footer", "nav"]
            ):
                element.extract()

            # Extrai texto com separação inteligente de linhas
            text = soup.get_text(separator="\n")

            # Limpeza de espaços em branco excessivos (mantendo parágrafos)
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            return "\n".join(chunk for chunk in chunks if chunk)
        except Exception:
            pass  # Fallback para Regex se o parser falhar

    # Fallback: Método Manual (Regex) - Frágil, mas funciona sem libs externas
    # Remove scripts e estilos
    text = re.sub(
        r"<(script|style).*?>.*?</\1>",
        "",
        html_content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Remove comentários
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Substitui quebras de linha por espaço
    text = re.sub(r"\n", " ", text)
    # Substitui tags de bloco por quebra de linha
    text = re.sub(r"</(p|div|h\d|li|ul|ol|br)>", "\n", text, flags=re.IGNORECASE)
    # Remove tags restantes
    text = re.sub(r"<[^>]+>", "", text)
    # Remove espaços múltiplos
    text = re.sub(r"\s+", " ", text).strip()
    return text


def learn_from_web(url: str, custom_title: str = None, verbose: bool = True) -> bool:
    """Baixa e processa uma URL para a base de conhecimento."""
    try:
        if verbose:
            common.console.print(f"[dim]🌐 Baixando: {url}[/dim]")

        # TENTATIVA 1: Crawl4AI (Container) - Renderização JS e Markdown Otimizado
        # Se o container estiver rodando, usamos ele para obter conteúdo de alta qualidade.
        try:
            # Timeout: 2s para conectar (fail fast se container off), 60s para renderizar
            crawl_res = requests.post(
                CRAWLER_API_URL, json={"urls": url, "priority": 10}, timeout=(2, 60)
            )
            if crawl_res.status_code == 200:
                data = crawl_res.json()
                markdown = data.get("markdown")
                if markdown:
                    if verbose:
                        common.console.print(
                            "[dim]🕷️  Processado via Crawl4AI (Container)[/dim]"
                        )
                    return save_knowledge(
                        url,
                        custom_title or data.get("metadata", {}).get("title"),
                        markdown,
                        verbose,
                    )
        except Exception as e:
            if verbose:
                common.console.print(
                    f"[dim yellow]⚠️  Crawl4AI indisponível ou falhou ({str(e)[:50]}...). Usando fallback local...[/dim]"
                )

        # TENTATIVA 2: Requests (Fallback) - HTML Estático
        # Headers para evitar bloqueio 403 em alguns sites
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        # Stream=True para baixar apenas headers primeiro
        response = requests.get(url, headers=headers, timeout=15, stream=True)

        # Validação de Content-Type para evitar baixar binários (PDF, ZIP, Imagens)
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type and "text/plain" not in content_type and "json" not in content_type:
            common.log_warning(f"Ignorando tipo de conteúdo não-texto: {content_type} em {url}")
            return False

        # FIX: Força encoding correto se não informado, evitando mojibake
        if response.encoding is None or response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding

        response.raise_for_status()

        # FIX: Limite de tamanho de download (5MB) para evitar OOM em arquivos gigantes
        MAX_SIZE = 5 * 1024 * 1024
        content_accumulated = []
        current_size = 0

        for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
            if chunk:
                content_accumulated.append(chunk)
                current_size += len(chunk)
                if current_size > MAX_SIZE:
                    common.log_warning(f"Conteúdo excedeu o limite de {MAX_SIZE} chars. Truncando.")
                    break

        full_text = "".join(content_accumulated)

        # Tenta extrair título se não fornecido
        if not custom_title:
            match = re.search(r"<title>(.*?)</title>", full_text, re.IGNORECASE)
            if match:
                custom_title = match.group(1).strip()
            else:
                custom_title = url.split("/")[-1] or "untitled"

        # Limpeza básica
        text_content = clean_html(full_text)

        if len(text_content) < 100:
            common.log_warning(f"Conteúdo muito curto para {url}. Ignorando.")
            return False

        return save_knowledge(url, custom_title, text_content, verbose)

    except Exception as e:
        common.log_error(f"Falha ao aprender de {url}: {e}")
        return False


def save_knowledge(
    url: str, title: str, content_text: str, verbose: bool = True
) -> bool:
    """Salva o conteúdo processado na base de conhecimento."""
    if not title:
        title = "untitled"

    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title)[:100]
    filename = f"web_{safe_title}.md"

    kb_dir = common.get_project_root() / "docs" / "knowledge_base"
    kb_dir.mkdir(parents=True, exist_ok=True)

    file_path = kb_dir / filename

    file_content = f"""---
source: {url}
ingested_at: {datetime.now().isoformat()}
agent: web_learner
---

# {title}

{content_text}
"""
    file_path.write_text(file_content, encoding="utf-8")
    if verbose:
        common.log_success(f"Conhecimento adquirido: {filename}")
    return True
