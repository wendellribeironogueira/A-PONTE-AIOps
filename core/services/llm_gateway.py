#!/usr/bin/env python3
import json
import functools
import os
import re
from pathlib import Path
import time
import random
from abc import ABC, abstractmethod

from core.lib import utils as common
from core.lib.sanitizer import InputSanitizer
from core.services import openrouter
from core.services import ollama


# --- FILOSOFIA DE CUSTO: LOCAL-FIRST E GRATUITO POR PADRÃO ---
# O A-PONTE é projetado para ser um portfólio de custo zero.
# O provedor padrão é 'ollama' (local).
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").lower()



# Definições Comportamentais (Contrato para Trainer/RAG)
APONTE_BEHAVIOR_DEFINITIONS = """
DIRETRIZES DE COMPORTAMENTO (RUNTIME):
1. PRAGMATISMO EXTREMO: Execute ferramentas imediatamente quando solicitado.
2. USO DE FERRAMENTAS: Prefira ferramentas nativas a comandos manuais.
"""

def is_available():
    return ollama.is_available()

@functools.lru_cache(maxsize=1)
def get_installed_models():
    return ollama.get_installed_models()

def get_active_model():
    """Retorna o modelo que será usado (Prioridade: aponte-ai > DEFAULT)."""
    if AI_PROVIDER == "openrouter" or AI_PROVIDER == "google":
        return os.getenv("OPENROUTER_MODEL", openrouter.DEFAULT_MODEL)

    # Lógica Ollama (Local)
    installed = ollama.get_installed_models()
    # Verifica se o modelo existe (com ou sem tag :latest)
    if "aponte-ai:latest" in installed:
        return "aponte-ai:latest"
    if "aponte-ai" in installed:
        return "aponte-ai"
    return ollama.DEFAULT_MODEL


def get_display_name(model=None):
    """Retorna um nome curto e amigável para o modelo ativo (UI Friendly)."""
    raw_name = model or get_active_model()

    if AI_PROVIDER != "ollama":
        provider_icon = "☁️"
        if AI_PROVIDER == "openrouter" or AI_PROVIDER == "google":
            provider_icon = "🌐"
        return f"{raw_name} ({provider_icon} {AI_PROVIDER.title()})"

    if "aponte-ai" in raw_name:
        return "A-PONTE AI"

    # Trata modelos locais (ex: deepseek-r1:1.5b)
    return f"{raw_name} (Local)"


def is_custom_brain_active():
    """Retorna True se o cérebro especializado (aponte-ai) estiver ativo."""
    # Se estiver usando provedor externo, o cérebro não está "ativo" no servidor (Modelfile),
    # então retornamos False para que o Architect injete o contexto via Prompt (RAG em tempo de execução).
    if AI_PROVIDER != "ollama":
        return False
    return get_active_model() == "aponte-ai" and AI_PROVIDER == "ollama"

# OTIMIZAÇÃO: Cache de configuração de modelos nano (Evita parsing repetitivo)
_NANO_CANDIDATES = os.getenv("APONTE_NANO_MODELS", "qwen2.5:0.5b,llama3.2:1b,qwen2.5:1.5b,deepseek-r1:1.5b").split(",")

def _resolve_target_model(requested_model, size_hint):
    """Resolve o modelo final com base na solicitação e no perfil de tamanho (Eficiência)."""
    if requested_model:
        return requested_model

    if size_hint == "nano" and AI_PROVIDER == "ollama":
        # Heurística: Tenta encontrar modelos leves instalados para tarefas rápidas
        installed = get_installed_models()
        for cand in _NANO_CANDIDATES:
            if cand in installed or f"{cand}:latest" in installed:
                return cand
    return get_active_model()

# --- STRATEGY PATTERN IMPLEMENTATION ---

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt, model, json_mode, verbose, timeout): pass
    
    @abstractmethod
    def chat(self, messages, model, tools, json_mode, verbose, timeout, status_callback): pass

class LocalProvider(LLMProvider):
    def generate(self, prompt, model, json_mode, verbose, timeout):
        try:
            return ollama.generate(prompt, model, json_mode, verbose, timeout)
        except Exception as e:
            common.console.print(f"[bold red]⚠️  Erro de comunicação com Ollama (generate): {e}[/]")
            return None

    def chat(self, messages, model, tools, json_mode, verbose, timeout, status_callback):
        try:
            return ollama.chat(messages, model, tools, json_mode, verbose, timeout, status_callback=status_callback)
        except Exception as e:
            common.console.print(f"[bold red]⚠️  Erro de comunicação com Ollama (chat): {e}[/]")
            return None

class CloudProvider(LLMProvider):
    def generate(self, prompt, model, json_mode, verbose, timeout):
        max_retries = 3
        base_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                # 🛡️ SANITIZAÇÃO: Remove segredos antes de enviar para a nuvem
                safe_prompt = InputSanitizer.clean(prompt)
                messages = [{"role": "user", "content": safe_prompt}]
                
                # Reutiliza a interface de chat para geração, comum em gateways como OpenRouter
                result = openrouter.chat(messages, model=model, temperature=0.1 if json_mode else 0.7)
                if result and result.get("content"):
                    return result["content"]
                
                raise ValueError("A API retornou uma resposta vazia.")

            except Exception as e:
                # Verifica por assinaturas de erro de rate limit (ex: status code 429)
                if "rate limit" in str(e).lower() or "429" in str(e):
                    if attempt < max_retries - 1:
                        delay = (base_delay ** attempt) + (random.random() * 0.5)
                        common.console.print(f"[dim yellow]⏳ Rate limit atingido (generate). Tentando novamente em {delay:.1f}s... (Tentativa {attempt + 1}/{max_retries})[/dim]")
                        time.sleep(delay)
                    else:
                        common.console.print(f"[bold red]❌ Rate limit excedido após {max_retries} tentativas. Abortando.[/bold red]")
                        return None
                else:
                    common.console.print(f"[bold yellow]⚠️  Provedor Cloud (generate) falhou: {e}[/bold yellow]")
                    return None
        return None

    def chat(self, messages, model, tools, json_mode, verbose, timeout, status_callback):
        max_retries = 3
        base_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                # 🛡️ SANITIZAÇÃO: Remove segredos antes de enviar para a nuvem
                safe_messages = [
                    {**msg, "content": InputSanitizer.clean(msg.get("content", ""))}
                    if isinstance(msg, dict) and msg.get("content")
                    else msg
                    for msg in messages
                ]

                result = openrouter.chat(safe_messages, tools=tools, model=model, temperature=0.1 if json_mode else 0.7)
                if result:
                    return result
                # Se a API retornar uma resposta vazia, considera uma falha e tenta novamente.
                raise ValueError("A API retornou uma resposta vazia.")

            except Exception as e:
                # Verifica por assinaturas de erro de rate limit (ex: status code 429)
                if "rate limit" in str(e).lower() or "429" in str(e):
                    if attempt < max_retries - 1:
                        # Exponential backoff com jitter para evitar thundering herd
                        delay = (base_delay ** attempt) + (random.random() * 0.5)
                        common.console.print(f"[dim yellow]⏳ Rate limit atingido. Tentando novamente em {delay:.1f}s... (Tentativa {attempt + 1}/{max_retries})[/dim]")
                        time.sleep(delay)
                    else:
                        common.console.print(f"[bold red]❌ Rate limit excedido após {max_retries} tentativas. Abortando.[/bold red]")
                        return None
                else:
                    # Para outros erros (ex: 500, erro de conexão), falha rapidamente.
                    common.console.print(f"[bold yellow]⚠️  Provedor Cloud (chat) falhou: {e}. Sinalizando para o orquestrador...[/bold yellow]")
                    return None
        return None

# SINGLETON INSTANCES (Efficiency: Avoid recreation on every call)
_LOCAL_PROVIDER = LocalProvider()
_CLOUD_PROVIDER = CloudProvider()

def generate(prompt, model=None, json_mode=False, verbose=True, timeout=120, provider=None, cached_content=None, size=None):
    """
    Envia um prompt para o modelo e retorna a resposta processada.
    Remove automaticamente tags de pensamento (<think>) do DeepSeek.
    """
    # Implementação da Estratégia de Modelos Híbridos (FUTURE_OPTIMIZATIONS.md)
    target_model = _resolve_target_model(model, size)
    target_provider = (provider or AI_PROVIDER).lower()

    provider_instance = _CLOUD_PROVIDER if target_provider in ["openrouter", "google"] else _LOCAL_PROVIDER
    try:
        return provider_instance.generate(prompt, target_model, json_mode, verbose, timeout)
    except Exception as e:
        common.console.print(f"[bold red]❌ Erro no Gateway LLM (generate): {e}[/bold red]")
        return None


def chat(messages, model=None, tools=None, json_mode=False, verbose=True, timeout=120, provider=None, cached_content=None, fallback_tools=None, status_callback=None, size=None):
    """
    Envia mensagens para a API de Chat do Ollama (Suporte a Native Tool Calling).
    Isso permite que o modelo decida usar ferramentas sem prompt engineering complexo (ReAct),
    economizando tokens e reduzindo latência.
    """
    
    # Implementação da Estratégia de Modelos Híbridos (FUTURE_OPTIMIZATIONS.md)
    target_model = _resolve_target_model(model, size)
    target_provider = (provider or AI_PROVIDER).lower()

    provider_instance = _CLOUD_PROVIDER if target_provider in ["openrouter", "google"] else _LOCAL_PROVIDER
    try:
        return provider_instance.chat(messages, target_model, tools, json_mode, verbose, timeout, status_callback)
    except Exception as e:
        common.console.print(f"[bold red]❌ Erro no Gateway LLM (chat): {e}[/bold red]")
        return None


def extract_code_block(text: str, language: str = None) -> str:
    """
    Extrai conteúdo de um bloco de código Markdown de forma robusta.
    Útil para processar respostas de agentes que geram código.
    """
    # Tenta encontrar bloco com linguagem específica ou genérico
    pattern = r"```(?:" + (language or r"\w+") + r")?\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)

    if match:
        return match.group(1).strip()

    # Fallback: Se não houver blocos, mas houver backticks soltos, limpa
    return text.replace("```", "").strip()


def start_server(force=False):
    return ollama.start_server(force)


def stop_server():
    return ollama.stop_server()


if __name__ == "__main__":
    # Teste rápido de conectividade e ciclo de vida (Self-Test)
    print("🔬 Executando diagnóstico do Gateway IA...")
    if start_server():
        try:
            print(f"🧠 Modelo Ativo: {get_active_model()}")
            print("💬 Enviando prompt de teste...")
            resp = generate("Responda com uma única palavra: OK", verbose=True)
            print(f"✅ Resposta recebida: {resp}")
        except KeyboardInterrupt:
            print("\n🛑 Interrompido pelo usuário.")
        except Exception as e:
            print(f"❌ Erro no teste: {e}")
        finally:
            stop_server()
