#!/usr/bin/env python3
import sys
import time
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.services import llm_gateway
from core.agents.architect import ArchitectAgent
from core.lib import utils as common

console = Console()


def check_ollama():
    console.print("[bold cyan]1. Verificando Conectividade Ollama...[/]")
    if llm_gateway.is_available():
        console.print("   ✅ Ollama está online e respondendo.")
        return True
    else:
        console.print("   ❌ Ollama offline ou inacessível.")
        return False


def check_model_semantics():
    console.print("\n[bold cyan]2. Verificando Semântica do Modelo (Persona)...[/]")
    model = llm_gateway.get_active_model()
    console.print(f"   🧠 Modelo Ativo: [bold]{model}[/]")

    # Prompt desafiador para verificar se o System Prompt foi carregado
    prompt = "Quem é você e qual seu escopo de atuação? Responda de forma sucinta."
    try:
        start = time.time()
        response = llm_gateway.generate(prompt, verbose=False)
        duration = time.time() - start

        console.print(f'   🤖 Resposta ({duration:.2f}s): [italic]"{response}"[/]')

        # Palavras-chave esperadas no System Prompt do A-PONTE
        keywords = ["A-PONTE", "AWS", "infraestrutura", "arquiteto", "DevSecOps"]
        matches = [k for k in keywords if k.lower() in response.lower()]

        if len(matches) >= 1:
            console.print(
                f"   ✅ Teste Semântico: [green]PASSOU[/] (Persona identificada: {', '.join(matches)})"
            )
            return True
        else:
            console.print(
                "   ⚠️ Teste Semântico: [yellow]ALERTA[/] (Resposta genérica. O modelo pode não estar especializado.)"
            )
            console.print(
                "      [dim]Dica: Execute 'aponte ai train' para reforçar a persona.[/dim]"
            )
            return True  # Warning, não erro crítico
    except Exception as e:
        console.print(f"   ❌ Erro na inferência: {e}")
        return False


def check_mcp_integration():
    console.print("\n[bold cyan]3. Verificando Integração MCP (Terraform)...[/]")
    try:
        # Instancia o agente sem input para não iniciar o loop interativo
        # Isso dispara o _init_terraform_mcp()
        agent = ArchitectAgent(initial_input="exit")

        if agent.tf_mcp:
            console.print("   ✅ Cliente MCP inicializado com sucesso.")

            # Teste de vida do processo MCP
            if agent.tf_mcp.process and agent.tf_mcp.process.poll() is None:
                console.print("   ✅ Processo MCP está rodando (PID ativo).")
                return True
            else:
                console.print("   ❌ Processo MCP morreu logo após início.")
                return False
        else:
            console.print("   ❌ Falha ao inicializar Cliente MCP (Objeto nulo).")
            return False
    except Exception as e:
        console.print(f"   ❌ Erro ao instanciar Agente/MCP: {e}")
        return False


def main():
    console.rule("[bold magenta]🩺 A-PONTE AI Core Healthcheck[/]")

    # Garante que o servidor Ollama esteja rodando (via Docker ou Local)
    if not llm_gateway.is_available():
        console.print("[dim]Tentando iniciar Ollama...[/dim]")
        llm_gateway.start_server()
        time.sleep(2)

    checks = [check_ollama, check_model_semantics, check_mcp_integration]

    success = True
    for check in checks:
        if not check():
            success = False
            console.print(
                "\n[bold red]⛔ Verificação interrompida por falha crítica.[/]"
            )
            break

    if success:
        console.rule("[bold green]🎉 Sistema de IA Íntegro[/]")
        sys.exit(0)
    else:
        console.rule("[bold red]💀 Falha na Integridade da IA[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
