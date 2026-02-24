import functools
import asyncio
import json
from typing import Any, Callable, Dict, Union

def truncate_output(content: Any, max_length: int = 12000) -> Any:
    """
    Trunca saídas longas para evitar estouro de contexto do LLM.
    Limite padrão: 12k caracteres (~3k tokens), seguro para modelos de 4k/8k.
    """
    if isinstance(content, str):
        if len(content) > max_length:
            return content[:max_length] + f"\n... [Output truncated by A-PONTE ({len(content)} chars)]"
    return content

def handle_mcp_errors(func: Callable) -> Callable:
    """
    Decorator para padronizar o tratamento de erros em ferramentas MCP.
    Captura exceções não tratadas e retorna um dicionário de erro estruturado.
    Suporta funções síncronas e assíncronas.
    """
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Retorna mensagem limpa para o LLM
            return {"error": str(e), "error_type": type(e).__name__}

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            return {"error": str(e), "error_type": type(e).__name__}

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper