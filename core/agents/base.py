#!/usr/bin/env python3
"""
Base Agent Class
----------------
Define a interface padrão para todos os agentes do sistema A-PONTE.
Garante consistência em logging, ciclo de vida e acesso a ferramentas.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from rich.console import Console
from rich.panel import Panel


class BaseAgent(ABC):
    """
    Classe abstrata que todo Agente deve herdar.
    Fornece identidade, memória e métodos de saída padronizados.
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.console = Console()
        self.memory: Dict[str, Any] = {}  # Memória de curto prazo do agente

    def log(self, message: str, style: str = "dim"):
        """Imprime uma mensagem no console com a identidade do agente."""
        self.console.print(f"[{style}]🤖 [{self.name}]: {message}[/{style}]")

    def log_success(self, message: str):
        self.log(f"✅ {message}", style="green")

    def log_warning(self, message: str):
        self.log(f"⚠️  {message}", style="yellow")

    def log_error(self, message: str):
        self.log(f"❌ {message}", style="red")

    def display_panel(
        self, content: str, title: Optional[str] = None, style: str = "blue"
    ):
        """Exibe um painel Rich formatado."""
        title_text = title if title else self.name
        self.console.print(Panel(content, title=title_text, border_style=style))

    @abstractmethod
    def run(self, *args, **kwargs) -> Any:
        """
        Lógica principal do agente.
        Deve ser implementada pelas subclasses.
        """
        pass
