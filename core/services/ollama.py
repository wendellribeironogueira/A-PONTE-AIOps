import os
import json
import subprocess
import time
import re
import shutil
from pathlib import Path
from core.lib import utils as common

try:
    import requests
except ImportError:
    import sys
    print("❌ Biblioteca 'requests' não encontrada. Execute: pip install requests")
    sys.exit(1)

# FIX: Usa IP explícito (127.0.0.1) para evitar delay de resolução DNS (IPv6/IPv4) e falhas em get_installed_models
_ollama_env = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
if _ollama_env.endswith("/api/generate"):
    _ollama_env = _ollama_env.replace("/api/generate", "")
OLLAMA_BASE_URL = _ollama_env.rstrip("/")
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"

_env_model = os.getenv("A_PONTE_AI_MODEL")
if _env_model and " " in _env_model:
    _env_model = None
DEFAULT_MODEL = _env_model or "qwen2.5-coder:1.5b"

def is_available():
    try:
        response = requests.get(OLLAMA_BASE_URL, timeout=1)
        if response.status_code == 200:
            return "Ollama is running" in response.text
        return False
    except Exception as e:
        if os.getenv("APONTE_DEBUG") == "1":
             print(f"[DEBUG] Ollama check failed: {e}")
        return False

def get_version():
    """Verifica a versão do servidor Ollama."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/version", timeout=0.5)
        if response.status_code == 200:
            return response.json().get("version", "unknown")
    except Exception as e:
        common.console.print(f"[dim]⚠️  Falha ao verificar versão do Ollama: {e}[/]")
    return "unknown"

def get_installed_models():
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            return [m["name"] for m in response.json().get("models", [])]
        return []
    except Exception as e:
        common.console.print(f"[dim yellow]⚠️  Falha ao listar modelos instalados: {e}[/]")
        return []

def start_server(force=False):
    if is_available():
        return True

    print("💤 Ollama está dormindo. Acordando o cérebro (Start)...")
    try:
        try:
            ollama_bin = shutil.which("ollama")
            print(f"🚀 Iniciando Ollama em modo nativo (Local Runtime)...")
            print(f"   📍 Binário: {ollama_bin}")
            proc = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            pid_file = common.get_project_root() / ".aponte-versions" / "ollama.pid"
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(str(proc.pid))

            for _ in range(30):
                if is_available():
                    print("⚡ Ollama pronto para o trabalho!")
                    return True
                time.sleep(1)
            print("❌ Timeout: Ollama local demorou muito para iniciar.")
            return False
        except FileNotFoundError:
            print("❌ Erro Crítico: Binário 'ollama' não encontrado no PATH. Instale via ollama.com")
            return False
    except Exception as e:
        print(f"❌ Falha ao iniciar Ollama: {e}")
        return False

def stop_server():
    if not is_available():
        return

    pid_file = common.get_project_root() / ".aponte-versions" / "ollama.pid"
    if not pid_file.exists():
        return

    print("🛏️ Tarefa finalizada. Colocando Ollama para dormir (Kill)...")
    try:
        if pid_file.exists():
            try:
                import psutil
                pid = int(pid_file.read_text().strip())
                if psutil.pid_exists(pid):
                    p = psutil.Process(pid)
                    p.terminate()
                    print(f"✅ Processo Ollama (PID {pid}) encerrado.")
                    pid_file.unlink()
                    return
            except Exception as e:
                print(f"⚠️ Falha ao encerrar processo PID {pid}: {e}")
        time.sleep(1)
        print("✅ Memória liberada.")
    except Exception as e:
        print(f"⚠️ Erro ao parar Ollama: {e}")

def chat(messages, model=None, tools=None, json_mode=False, verbose=True, timeout=300, status_callback=None):
    target_model = model
    if not target_model:
        installed = get_installed_models()
        if "aponte-ai:latest" in installed:
            target_model = "aponte-ai:latest"
        elif "aponte-ai" in installed:
            target_model = "aponte-ai"
        else:
            target_model = DEFAULT_MODEL

    if target_model and " " in target_model:
        target_model = DEFAULT_MODEL

    if not is_available():
        start_server(force=True)

    # GUARDRAIL: Verificação de Compatibilidade de Versão
    # Qwen2.5 e modelos novos exigem Ollama v0.3+ para funcionar corretamente.
    ver = get_version()
    if ver and (ver.startswith("0.0") or ver.startswith("0.1")):
        common.console.print(f"\n[bold red]⛔ ALERTA CRÍTICO: Versão do Ollama obsoleta ({ver}).[/]")
        common.console.print("[yellow]O modelo Qwen2.5 requer Ollama v0.3.0+. O sistema pode travar ou alucinar.[/]")
        common.console.print("[yellow]👉 Solução: Execute 'curl -fsSL https://ollama.com/install.sh | sh' para atualizar.[/]\n")

    installed = get_installed_models()
    model_found = target_model in installed
    if not model_found and ":" not in target_model and f"{target_model}:latest" in installed:
        model_found = True

    if not model_found:
        if verbose:
            common.console.print(f"[bold yellow]⬇️  Modelo '{target_model}' não encontrado. Iniciando download automático...[/]")
        try:
            requests.post(f"{OLLAMA_BASE_URL}/api/pull", json={"name": target_model}, timeout=600)
        except Exception as e:
            common.console.print(f"[dim red]⚠️  Falha no download automático do modelo: {e}[/]")

    # LÓGICA DE PRESERVAÇÃO DO MODELFILE (Encapsulada no Driver)
    # Se o modelo for especializado (aponte-ai), a API do Ollama sobrescreve o System Prompt do Modelfile
    # se enviarmos uma mensagem com role="system".
    # Aqui, interceptamos isso e convertemos para "user" para preservar o cérebro treinado.
    final_messages = messages
    if "aponte-ai" in target_model:
        final_messages = []
        for m in messages:
            if m["role"] == "system":
                # FIX: Sempre preserva o Modelfile (Identity) convertendo System -> User.
                # Preserva a identidade do modelo treinado.
                # O contexto foi ajustado para 4096 para suportar hardware modesto.
                final_messages.append({"role": "user", "content": f"--- CONTEXTO DA SESSÃO ---\n{m['content']}\n------------------------"})
            else:
                final_messages.append(m)

    payload = {
        "model": target_model,
        "messages": final_messages,
        "stream": True, # FIX: Streaming ativado para evitar timeout e "mudez"
        "keep_alive": "30m",
        "options": {
            "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", 4096)), # FIX: Reduzido para 4096 para evitar Swap/Travamento
            "temperature": 0.0, # FIX: Zero absoluto para máxima precisão em hardware modesto
        },
    }

    # Otimização de Threads: Se definido no env, usa. Senão, deixa o Ollama decidir (Auto).
    if os.getenv("OLLAMA_NUM_THREAD"):
        payload["options"]["num_thread"] = int(os.getenv("OLLAMA_NUM_THREAD"))

    if tools:
        payload["tools"] = tools

    if json_mode:
        payload["format"] = "json"

    try:
        if verbose:
            tools_info = f" | Tools: {len(tools)}" if tools else ""
            common.console.print(f"[bold cyan]🤖 Chat com {target_model} (Ctx: {payload['options']['num_ctx']}{tools_info})...[/]")

        max_retries = 2
        for attempt in range(max_retries):
            try:
                # FIX: Usa stream=True e consome a resposta iterativamente
                response = requests.post(OLLAMA_CHAT_URL, json=payload, stream=True, timeout=timeout)
                response.raise_for_status()

                full_content = []
                tool_calls = []

                for line in response.iter_lines():
                    if line:
                        body = json.loads(line)
                        if "error" in body:
                            raise RuntimeError(body["error"])

                        # FIX: Processa mensagem independente do status 'done' para evitar perda de dados em respostas curtas (Single Chunk)
                        msg = body.get("message", {})
                        if "content" in msg and msg["content"]:
                            full_content.append(msg["content"])
                            # Feedback visual: Mostra que o cérebro está trabalhando
                            if status_callback and len(full_content) % 5 == 0:
                                status_callback(f"🤖 Gerando ({len(full_content)} tokens)...")

                        if "tool_calls" in msg:
                            tool_calls.extend(msg["tool_calls"])

                        if body.get("done"):
                            break

                message = {
                    "role": "assistant",
                    "content": "".join(full_content),
                }
                if tool_calls:
                    message["tool_calls"] = tool_calls

                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise e

        if message.get("content"):
             message["content"] = re.sub(r"<think>.*?(?:</think>|$)", "", message["content"], flags=re.DOTALL).strip()

        if verbose and message.get("tool_calls"):
            common.console.print(f"[dim]🔧 Modelo solicitou {len(message['tool_calls'])} ferramenta(s).[/dim]")

        return message

    except requests.exceptions.HTTPError as e:
        if e.response is not None:
             if e.response.status_code == 400 and "does not support tools" in e.response.text and tools:
                 if verbose:
                     common.console.print(f"[yellow]⚠️  Modelo '{target_model}' não suporta ferramentas nativas. Alternando para modo texto (ReAct)...[/]")
                 payload.pop("tools", None)
                 try:
                     response = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=600)
                     response.raise_for_status()
                     result = response.json()
                     message = result.get("message", {})
                     if message.get("content"):
                         message["content"] = re.sub(r"<think>.*?(?:</think>|$)", "", message["content"], flags=re.DOTALL).strip()
                     return message
                 except Exception as retry_e:
                     common.console.print(f"[red]❌ Falha no fallback ReAct: {retry_e}[/]")
                     return None
             raise RuntimeError(f"Erro API Ollama ({e.response.status_code}): {e.response.text}")
    except Exception as e:
        raise RuntimeError(f"Erro no Chat Ollama: {e}")

def generate(prompt, model=None, json_mode=False, verbose=True, timeout=300):
    target_model = model or DEFAULT_MODEL
    if target_model and " " in target_model:
        target_model = DEFAULT_MODEL

    messages = [{"role": "user", "content": prompt}]
    try:
        response = chat(messages, target_model, None, json_mode, verbose, timeout)
        if response and response.get("content"):
            return response["content"]
        return "[ERRO] Resposta vazia do modelo."
    except Exception as e:
        return f"[ERRO] Falha na geração: {str(e)}"