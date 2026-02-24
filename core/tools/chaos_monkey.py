#!/usr/bin/env python3
import random
import subprocess
import sys
import time
from pathlib import Path

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common

def main():
    common.console.rule("[bold red]🔥 A-PONTE Chaos Monkey[/]")

    # Lista containers rodando
    try:
        res = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True
        )
        containers = [c for c in res.stdout.splitlines() if c.strip()]
    except Exception as e:
        common.log_error(f"Falha ao listar containers: {e}")
        sys.exit(1)

    # Filtra containers seguros (não matar o próprio monkey ou banco de dados persistente se não quiser perder dados)
    # Matar o mcp-terraform é interessante para testar resiliência do wrapper
    targets = [c for c in containers if "postgres" not in c and "ollama" not in c]

    if not targets:
        common.console.print("[yellow]Nenhum alvo válido para o caos (bancos de dados e IA são protegidos).[/]")
        return

    target = random.choice(targets)

    common.console.print(f"🎯 Alvo selecionado: [bold cyan]{target}[/]")
    common.console.print("🔫 Disparando falha em 3... 2... 1...")
    time.sleep(2)

    try:
        subprocess.run(["docker", "kill", target], check=True)
        common.log_success(f"Container {target} abatido com sucesso!")
        common.console.print("[dim]O sistema deve ser capaz de se recuperar (auto-healing) ou falhar graciosamente.[/dim]")
    except Exception as e:
        common.log_error(f"Falha ao matar container: {e}")

if __name__ == "__main__":
    main()
