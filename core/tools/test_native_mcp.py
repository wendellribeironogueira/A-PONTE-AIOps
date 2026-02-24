#!/usr/bin/env python3
import sys
from rich.console import Console
from core.lib.mcp import MCPClient

console = Console()


def main():
    # Usa o interpretador Python atual para rodar o servidor
    cmd = [sys.executable, "core/services/mcp_aws_reader.py"]

    console.print("[bold green]🚀 Testando Servidor MCP Nativo (Python)...[/]")
    client = MCPClient(command=cmd)
    client.start()

    tools = client.list_tools()
    for t in tools:
        console.print(f"🛠️  Tool: [cyan]{t['name']}[/] - {t['description']}")


if __name__ == "__main__":
    main()
