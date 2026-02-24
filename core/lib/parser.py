import json
import re
import shlex
from typing import Any, Dict, List, Optional


class ResponseParser:
    """
    Middleware para processar respostas textuais e estruturadas de LLMs.
    Extrai blocos de código, chamadas de ferramentas e intenções,
    isolando a lógica de Regex do Agente principal.
    """

    @staticmethod
    def extract_code_blocks(text: str, language: str = "hcl") -> List[str]:
        """
        Extrai blocos de código markdown.
        Suporta variações como ```hcl, ```terraform ou apenas ```.
        """
        # Regex robusto para capturar blocos, ignorando case
        pattern = rf"```(?:{language}|terraform)?\n(.*?)```"
        return re.findall(pattern, text, re.DOTALL | re.IGNORECASE)

    @staticmethod
    def extract_tool_call(text: str) -> Optional[str]:
        """Extrai comando RUN_TOOL do texto."""
        # Padrão: RUN_TOOL: `comando` ou RUN_TOOL: comando
        match = re.search(r"RUN_TOOL:\s*`?([^`\n]+)`?", text)
        if match:
            cmd = match.group(1).strip()
            # Limpeza de artefatos de Markdown (negrito) que a IA possa ter inserido
            return cmd.replace("**", "").strip()
        return None

    @staticmethod
    def extract_resource_read(text: str) -> Optional[str]:
        """Extrai comando READ_RESOURCE do texto."""
        match = re.search(r"READ_RESOURCE:\s*`?([^`\n]+)`?", text)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def extract_json_tool_call(text: str) -> Optional[str]:
        """Tenta extrair uma chamada de ferramenta em formato JSON puro (Ollama/Llama3)."""
        try:
            # Procura por objeto JSON isolado ou no início
            text = text.strip()
            if text.startswith("{") and '"name":' in text:
                data = json.loads(text)
                name = data.get("name")
                params = data.get("parameters", {})
                # Converte para formato RUN_TOOL
                args_str = " ".join([f"{k}={shlex.quote(str(v))}" for k, v in params.items()])
                return f"{name} {args_str}"
        except Exception:
            pass
        return None

    @staticmethod
    def parse_native_tool_calls(tool_calls: List[Dict[str, Any]]) -> str:
        """Converte chamadas de ferramenta nativas (JSON) para formato texto (RUN_TOOL)."""
        output = ""
        for tool in tool_calls:
            func = tool.get("function", {})
            name = func.get("name")
            args = func.get("arguments", {})

            # Robustez: Alguns provedores (Ollama/OpenAI) retornam argumentos como string JSON
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            # Converte args dict para string de comando (compatibilidade com _execute_tool)
            # Ex: tf_plan project_name='foo bar'
            # FIX: Usa shlex.quote para lidar corretamente com aspas e espaços nos valores
            args_str = " ".join([f"{k}={shlex.quote(str(v))}" for k, v in args.items()])
            cmd = f"{name} {args_str}"
            output += f"\nRUN_TOOL: {cmd}"
        return output
