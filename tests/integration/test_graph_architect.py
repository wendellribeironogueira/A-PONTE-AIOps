import unittest
from unittest.mock import MagicMock
import sys
from pathlib import Path

# Adiciona raiz do projeto ao path para imports funcionarem
project_root = Path(__file__).parents[2].resolve()
sys.path.append(str(project_root))

from core.agents.graph_architect import GraphArchitect
from core.lib.mcp_manager import ToolManager

class TestGraphArchitectIntegration(unittest.TestCase):
    """
    Teste de Integração para o Orquestrador Cognitivo (GraphArchitect).
    Valida a construção do grafo e a injeção de dependências.
    """

    def setUp(self):
        # Mock do ToolManager para não depender de ferramentas reais/Docker
        self.mock_tool_manager = MagicMock(spec=ToolManager)
        self.mock_tool_manager.tools_definitions = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]

    def test_graph_compilation(self):
        """Verifica se o grafo é compilado sem erros."""
        try:
            architect = GraphArchitect(tool_manager=self.mock_tool_manager)
            self.assertIsNotNone(architect.graph, "O grafo não deve ser None após inicialização")

            # Verifica se o grafo compilado é executável (tem método invoke ou stream)
            self.assertTrue(hasattr(architect.graph, "invoke"), "O grafo compilado deve ter método 'invoke'")

        except Exception as e:
            self.fail(f"Falha ao inicializar GraphArchitect: {e}")

if __name__ == "__main__":
    unittest.main()