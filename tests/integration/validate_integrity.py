#!/usr/bin/env python3
import sys
from pathlib import Path

# Tenta importar rich para output bonito, com fallback
try:
    from rich.console import Console
except ImportError:

    class Console:
        def print(self, *args, **kwargs):
            print(*args)


console = Console()


def main():
    # Define a raiz do projeto (assumindo que este script está em tests/)
    root_dir = Path(__file__).parent.parent

    console.print(f"[dim]🔍 Verificando integridade estrutural em: {root_dir}[/dim]")

    # Lista de verificação de arquivos essenciais
    checklist = {
        "Core": ["Makefile", "scripts/menu.py", "scripts/common.py"],
        "IA Ops": [
            "ia_ops/pipeline.py",
            "ia_ops/git_auditor.py",
            "ia_ops/security_auditor.py",
        ],
        "Infra": ["terraform"],
        "Config": ["projects"],
    }

    missing = []

    for category, items in checklist.items():
        for item in items:
            path = root_dir / item
            if not path.exists():
                missing.append(f"[{category}] {item}")

    # Verifica se o contexto existe (aviso apenas)
    if not (root_dir / ".bridge_context").exists():
        console.print(
            "[yellow]⚠️  Arquivo .bridge_context não encontrado (será recriado pelo menu).[/]"
        )

    if missing:
        console.print(
            "[bold red]❌ Falhas de Integridade Detectadas (Arquivos Ausentes):[/]"
        )
        for m in missing:
            console.print(f"   - {m}")
        sys.exit(1)

    console.print("[bold green]✅ Estrutura do projeto validada com sucesso![/]")
    sys.exit(0)


if __name__ == "__main__":
    main()
