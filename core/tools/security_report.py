#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    print("❌ Biblioteca 'rich' não encontrada. Execute: pip install rich")
    sys.exit(1)

console = Console()

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common  # noqa: E402


def load_report(filepath):
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        console.print(f"[red]Erro ao ler relatório: {e}[/]")
        sys.exit(1)


def generate_table(findings):
    if not findings:
        console.print(
            Panel(
                "[green]✅ Nenhum problema de segurança encontrado! Seu código está limpo.[/]",
                border_style="green",
            )
        )
        return

    # Ordenação por Severidade (Crítico primeiro)
    severity_order = {
        "CRITICAL": 0,
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3,
        "INFO": 4,
        "UNKNOWN": 5,
    }
    findings.sort(key=lambda x: severity_order.get(x.get("severity", "UNKNOWN"), 99))

    table = Table(
        title="🛡️  Relatório de Segurança Unificado (A-PONTE)",
        box=box.ROUNDED,
        header_style="bold magenta",
    )
    table.add_column("Sev", justify="center", style="bold")
    table.add_column("Ferramenta", style="cyan")
    table.add_column("ID / Check", style="dim")
    table.add_column("Descrição", style="white")
    table.add_column("Local", style="blue")

    for f in findings:
        sev = f.get("severity", "UNKNOWN")
        style = "white"
        if sev == "CRITICAL":
            style = "red blink"
        elif sev == "HIGH":
            style = "red"
        elif sev == "MEDIUM":
            style = "yellow"
        elif sev == "LOW":
            style = "blue"

        # Formata localização
        loc = f.get("resource_id") or f.get("file_path", "N/A")
        if f.get("line"):
            loc += f":{f.get('line')}"

        table.add_row(
            f"[{style}]{sev}[/]",
            f.get("tool", "unknown"),
            f.get("check_id", "N/A"),
            f.get("title", "")[:80],  # Trunca títulos muito longos
            loc,
        )

    console.print(table)

    # Estatísticas Finais
    counts = Counter(f.get("severity", "UNKNOWN") for f in findings)
    stats = " | ".join(
        [
            f"[bold {('red' if k in ['CRITICAL','HIGH'] else 'white')}]{k}: {v}[/]"
            for k, v in counts.items()
        ]
    )
    console.print(Panel(f"📊 [bold]Resumo:[/bold] {stats}", border_style="dim"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A-PONTE Security Reporter")
    parser.add_argument("--file", help="Arquivo JSON de relatório (Opcional)")
    parser.add_argument("--project", help="Nome do projeto (Opcional)")
    args = parser.parse_args()

    filepath = args.file

    if not filepath:
        project = args.project or common.read_context()
        if project and project != "home":
            # Tenta localizar o relatório centralizado
            central_path = (
                project_root / "logs" / "security_reports" / f"{project}.json"
            )
            if central_path.exists():
                filepath = central_path
                console.print(
                    f"[dim]📂 Lendo relatório centralizado: {central_path.name}[/dim]"
                )
            else:
                console.print(
                    f"[yellow]⚠️  Relatório não encontrado para '{project}' em logs/security_reports/.[/]"
                )
                sys.exit(1)
        else:
            console.print(
                "[red]❌ Erro: Forneça --file ou defina um contexto de projeto.[/]"
            )
            sys.exit(1)

    findings = load_report(filepath)
    generate_table(findings)
