import json
import subprocess
import os
import sys
from typing import Any, Dict, List, Optional


class MCPClient:
    """
    Cliente para comunicação com servidores MCP rodando em Docker.
    Gerencia o ciclo de vida do processo e o protocolo JSON-RPC.
    """

    def __init__(
        self,
        docker_image: Optional[str] = None,
        command: Optional[List[str]] = None,
        silent: bool = False,
        cwd: Optional[str] = None,
    ):
        self.docker_image = docker_image
        self.command = command
        self.silent = silent
        self.cwd = cwd
        self.process = None
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def start(self):
        """Inicia o processo MCP (Docker ou Local)."""
        if self.docker_image:
            cmd = [
                "docker",
                "run",
                "--rm",
                "-i",
                "-v",
                f"{os.getcwd()}:/app",
                "-w",
                "/app",
                self.docker_image,
            ]
        elif self.command:
            cmd = self.command
        else:
            raise ValueError(
                "Configuração inválida: forneça 'docker_image' ou 'command' para iniciar o MCP."
            )

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, # Captura stderr sempre para diagnóstico de crash
            text=True,
            cwd=self.cwd,
            bufsize=1,  # Line buffered para text mode
        )
        self._handshake()

    def _handshake(self):
        """Realiza a inicialização do protocolo MCP."""
        # 1. Initialize Request
        req_id = self._next_id()
        init_req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aponte-core", "version": "2.0"},
            },
        }
        self._send(init_req)
        self._read_response(req_id)  # Aguarda resposta do init

        # 2. Initialized Notification
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def list_tools(self) -> List[Dict[str, Any]]:
        """Lista as ferramentas disponíveis no servidor MCP."""
        req_id = self._next_id()
        req = {"jsonrpc": "2.0", "id": req_id, "method": "tools/list"}
        self._send(req)
        response = self._read_response(req_id)

        if "error" in response:
            return []

        return response.get("result", {}).get("tools", [])

    def list_resources(self) -> List[Dict[str, Any]]:
        """Lista os recursos disponíveis no servidor MCP."""
        req_id = self._next_id()
        req = {"jsonrpc": "2.0", "id": req_id, "method": "resources/list"}
        self._send(req)
        response = self._read_response(req_id)

        if "error" in response:
            return []

        return response.get("result", {}).get("resources", [])

    def read_resource(self, uri: str) -> Dict[str, Any]:
        """Lê o conteúdo de um recurso específico."""
        req_id = self._next_id()
        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "resources/read",
            "params": {"uri": uri},
        }
        self._send(req)
        response = self._read_response(req_id)
        if "error" in response:
            return {"contents": [{"text": f"MCP Error: {response['error'].get('message')}"}]}
        return response.get("result", {})

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoca uma ferramenta específica no servidor MCP."""
        req_id = self._next_id()
        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        self._send(req)
        response = self._read_response(req_id)
        if "error" in response:
            return {"content": [{"type": "text", "text": f"MCP Error: {response['error'].get('message')}"}]}
        return response.get("result", {})

    def _send(self, data: Dict):
        if self.process and self.process.stdin:
            self.process.stdin.write(json.dumps(data) + "\n")
            self.process.stdin.flush()

    def _read_response(self, req_id: int) -> Dict:
        while self.process and self.process.stdout:
            line = self.process.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
                if msg.get("id") == req_id:
                    return msg
            except json.JSONDecodeError:
                continue
        return {}
