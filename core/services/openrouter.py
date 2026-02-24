import os
import json
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional

# Tenta carregar variáveis do .env (Suporte a execução direta)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[2] / ".env")
except ImportError:
    pass

# Modelo padrão gratuito e confiável (baseado nos seus logs)
# O usuário pode sobrescrever isso via env var OPENROUTER_MODEL
DEFAULT_MODEL = "google/gemini-2.0-flash-lite-preview-02-05:free"

def chat(messages: List[Dict], tools: Optional[List[Dict]] = None, model: str = None, **kwargs) -> Dict:
    """
    Envia mensagens para a API do OpenRouter (formato OpenAI-compatible).
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip().strip('"').strip("'")

    # Correção robusta: Remove sinal de igual (=) inicial que pode vir de erros de formatação no .env
    if api_key.startswith("="):
        api_key = api_key.lstrip("=").strip()

    if not api_key:
        print("⚠️  OPENROUTER_API_KEY não encontrada no ambiente.")
        return None

    # Seleção de modelo: Argumento > Env Var > Default
    model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/aponte-platform", # Requerido pelo OpenRouter para ranking
        "X-Title": "A-PONTE CLI",
        "Content-Type": "application/json"
    }

    # Sanitização de parâmetros para evitar erros 400
    temperature = kwargs.get("temperature", 0.7)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    # Injeção de Ferramentas (Se o modelo suportar)
    # Nota: Modelos 'free' podem ter dificuldade com tool calling complexo.
    if tools:
        payload["tools"] = tools
        # payload["tool_choice"] = "auto" # Opcional, padrão é auto

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120 # Timeout maior para modelos gratuitos que podem ter fila
        )

        if response.status_code != 200:
            # Tratamento específico para modelos que não suportam tools (404 no OpenRouter)
            if response.status_code == 404 and "support tool use" in response.text and tools:
                print(f"❌ O modelo '{model}' não suporta 'tool calling' nativo no OpenRouter.")
                print(f"   Ação Requerida: Use um modelo compatível com ferramentas, como '{DEFAULT_MODEL}'.")
                print("   Dica: Verifique/Remova a variável OPENROUTER_MODEL no seu arquivo .env")
                return None

            if response.status_code != 200:
                if response.status_code == 401:
                    masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "INVALID"
                    print(f"❌ Erro de Autenticação (401). Chave carregada: '{masked}' (Len: {len(api_key)})")
                    print("   Dica: Verifique se há aspas ou espaços extras no arquivo .env")
                print(f"❌ Erro OpenRouter ({response.status_code}): {response.text}")
                return None

        data = response.json()

        # Normalização da resposta para o formato interno do A-PONTE
        if "choices" in data and len(data["choices"]) > 0:
            choice = data["choices"][0]
            message = choice.get("message", {})

            return {
                "content": message.get("content"),
                "tool_calls": message.get("tool_calls")
            }

    except Exception as e:
        print(f"❌ Exceção na comunicação com OpenRouter: {e}")
        return None