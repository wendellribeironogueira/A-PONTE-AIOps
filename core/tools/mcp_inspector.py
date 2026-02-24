#!/usr/bin/env python3
from rich.console import Console
from rich.table import Table
from core.lib.mcp import MCPClient

console = Console()


def inspect_service(service_name, script_path):
    container_name = "mcp-terraform"
    console.print(f"[dim]🔌 Conectando a {service_name} ({container_name})...[/dim]")

    try:
        # Conecta ao container rodando via docker exec
        command = ["docker", "exec", "-i", container_name, "python3", script_path]
        client = MCPClient(command=command, silent=True)
        client.start()
        tools = client.list_tools()
        return tools
    except Exception:
        # O erro BrokenPipe ocorre se o script falhar logo no início (ex: import error)
        # O stderr do docker exec já mostra o erro real (ModuleNotFoundError)
        return []


def main():
    console.rule("[bold magenta]🕵️  MCP Inspector[/]")

    # Lista de serviços MCP para inspecionar
    services = [
        ("Terraform", "/app/core/services/mcp_terraform.py"),
        ("Git", "/app/core/services/mcp_git.py"),
        ("AWS Reader", "/app/core/services/mcp_aws_reader.py"),
    ]

    all_tools = []

    for name, path in services:
        tools = inspect_service(name, path)
        for t in tools:
            t["source"] = name
        all_tools.extend(tools)

    if not all_tools:
        console.print("\n[bold red]❌ Nenhuma ferramenta encontrada.[/]")
        console.print(
            "[yellow]Diagnóstico:[/yellow] O container 'mcp-terraform' pode estar desatualizado."
        )
        console.print(
            "👉 O erro [bold]'ModuleNotFoundError: No module named fastmcp'[/] indica que a imagem Docker precisa ser reconstruída."
        )
        console.print(
            "\n[bold green]Solução:[/bold green] Execute [bold cyan]aponte sandbox build[/] e tente novamente."
        )
        return

    table = Table(title="🛠️  Catálogo de Ferramentas (Sandbox)")
    table.add_column("Origem", style="blue")
    table.add_column("Ferramenta", style="cyan", no_wrap=True)
    table.add_column("Descrição", style="magenta")

    for tool in all_tools:
        table.add_row(
            tool["source"], tool["name"], tool.get("description", "Sem descrição")
        )

    console.print(table)
    console.print(f"\n[green]✅ Total de ferramentas carregadas: {len(all_tools)}[/]")


if __name__ == "__main__":
    main()
