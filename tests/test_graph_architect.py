import sys
import os
from pathlib import Path

# Adiciona a raiz do projeto ao path para imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from unittest.mock import MagicMock, patch
from core.agents.graph_architect import GraphArchitect
from langchain_core.messages import HumanMessage, AIMessage

class TestGraphArchitect:
    @pytest.fixture
    def mock_tool_manager(self):
        manager = MagicMock()
        manager.tools_definitions = []
        return manager

    @patch("core.agents.graph_architect.llm_gateway")
    def test_initialization(self, mock_gateway, mock_tool_manager):
        """Valida se o grafo é compilado corretamente na inicialização."""
        architect = GraphArchitect(mock_tool_manager)
        assert architect.graph is not None

    @patch("core.agents.graph_architect.llm_gateway")
    def test_planner_node(self, mock_gateway, mock_tool_manager):
        """Valida se o nó de planejamento converte a intenção em passos."""
        architect = GraphArchitect(mock_tool_manager)
        state = {"messages": [HumanMessage(content="Deploy EC2")]}

        # Mock LLM returning a JSON plan
        mock_gateway.chat.return_value = {"content": '["Terraform Init", "Terraform Apply"]'}

        result = architect._planner_node(state)

        assert result["plan"] == ["Terraform Init", "Terraform Apply"]
        assert result["current_step"] == 0
        assert result["error"] is None

    @patch("core.agents.graph_architect.llm_gateway")
    def test_executor_node_tool_call(self, mock_gateway, mock_tool_manager):
        """Valida se o executor detecta chamadas de ferramenta."""
        architect = GraphArchitect(mock_tool_manager)
        state = {
            "messages": [],
            "plan": ["Run Init"],
            "current_step": 0,
            "tool_outputs": {}
        }

        # Mock LLM returning a tool call
        mock_gateway.chat.return_value = {
            "content": "Running init...",
            "tool_calls": [{"function": {"name": "tf_init", "arguments": "{}"}}]
        }

        result = architect._executor_node(state)

        message = result["messages"][0]
        assert isinstance(message, AIMessage)
        assert "tool_calls" in message.additional_kwargs
        assert message.additional_kwargs["tool_calls"][0]["function"]["name"] == "tf_init"

if __name__ == "__main__":
    pytest.main([__file__])