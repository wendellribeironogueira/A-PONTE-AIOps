#!/usr/bin/env python3
import os
import sys
from pathlib import Path

from rich.prompt import Prompt

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common


def configure_api_key(lines, key_name, key_url, prompt_text):
    """Função genérica para configurar uma API key."""
    key = ""
    # Verifica se já existe
    has_key = any(l.startswith(f"{key_name}=") for l in lines)
    if has_key:
        if (
            Prompt.ask(
                f"Chave {key_name} já configurada. Deseja substituí-la?",
                choices=["s", "n"],
                default="n",
            )
            == "n"
        ):
            return lines, "KEEP"

    common.console.print(
        f"[dim]A API Key será salva localmente em .env e não será versionada.[/dim]"
    )
    common.console.print(f"[dim]Obtenha sua chave em: {key_url}[/dim]")
    key = Prompt.ask(prompt_text)

    if not key.strip():
        common.log_error("Chave vazia. Operação cancelada.")
        return lines, "EMPTY"

    # Remove chave antiga e adiciona nova
    lines = [l for l in lines if not l.startswith(f"{key_name}=")]
    lines.append(f"{key_name}={key.strip()}")
    common.log_success(f"Chave {key_name} atualizada.")
    return lines, "OK"


def main():
    common.console.rule("[bold cyan]🔑 Configuração do Cérebro da IA (A-PONTE)[/]")

    env_file = common.get_project_root() / ".env"
    lines = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()

    # 1. Configuração do Modelo (Cérebro Padrão)
    common.console.print("\n[bold cyan]🧠 Seleção de Cérebro (Modelo Padrão)[/]")
    models = {
        "1": "meta-llama/llama-3.3-70b-instruct:free (OpenRouter - Recomendado)",
        "2": "google/gemini-2.0-flash-exp:free (OpenRouter - Contexto 1M)",
        "3": "nousresearch/hermes-3-405b-instruct:free (OpenRouter - Mais Inteligente)",
        "4": "deepseek-r1:1.5b (Local/Offline - Sem custo de API)",
    }

    for k, v in models.items():
        common.console.print(f" [{k}] {v}")

    choice = Prompt.ask(
        "Escolha o modelo padrão", choices=list(models.keys()), default="1"
    )

    model_map = {
        "1": "meta-llama/llama-3.3-70b-instruct:free",
        "2": "google/gemini-2.0-flash-exp:free",
        "3": "nousresearch/hermes-3-405b-instruct:free",
        "4": "deepseek-r1:1.5b",
    }
    selected_model = model_map[choice]

    # 2. Configuração da API Key correspondente
    if "free" in selected_model or "/" in selected_model:
        lines, status = configure_api_key(
            lines,
            "OPENROUTER_API_KEY",
            "https://openrouter.ai/keys",
            "Cole sua OpenRouter API Key",
        )
        if status == "EMPTY":
            return

    # 3. Salva as configurações no .env
    lines = [l for l in lines if not l.startswith("A_PONTE_AI_MODEL=")]
    lines.append(f'A_PONTE_AI_MODEL="{selected_model}"')

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    common.log_success(f"Configurações salvas em {env_file}")
    common.console.print(
        "[dim]Para aplicar agora: [bold]source .env[/bold] ou reinicie o terminal.[/dim]"
    )


if __name__ == "__main__":
    main()
