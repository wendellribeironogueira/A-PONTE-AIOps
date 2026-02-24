from typing import Any, Dict, List, Optional, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model, PrivateAttr

class MCPToolAdapter(BaseTool):
    """
    Adaptador que permite usar ferramentas do A-PONTE MCP dentro do ecossistema LangChain.
    Converte a definição de ferramenta MCP para LangChain BaseTool, mantendo a validação Pydantic.
    """
    name: str
    description: str
    args_schema: Optional[Type[BaseModel]] = None

    # Atributos privados para manter o estado do gerenciador sem interferir na serialização do LangChain
    _tool_manager: Any = PrivateAttr()
    _context_resolver: Any = PrivateAttr()
    _audit_logger: Any = PrivateAttr()

    def __init__(self, name: str, description: str, tool_manager: Any, schema: Dict, context_resolver: Any, audit_logger: Any, **kwargs):
        # Criação dinâmica do modelo Pydantic para validação de argumentos baseada no schema JSON
        pydantic_model = self._create_pydantic_model(name, schema)
        super().__init__(name=name, description=description, args_schema=pydantic_model, **kwargs)
        self._tool_manager = tool_manager
        self._context_resolver = context_resolver
        self._audit_logger = audit_logger

    def _create_pydantic_model(self, name: str, schema: Dict) -> Type[BaseModel]:
        """Cria um modelo Pydantic dinâmico a partir do schema JSON da ferramenta."""
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        fields = {}
        for field_name, field_info in properties.items():
            field_type = str
            type_str = field_info.get("type")

            if type_str == "integer":
                field_type = int
            elif type_str == "boolean":
                field_type = bool
            elif type_str == "array":
                field_type = list
            elif type_str == "number":
                field_type = float

            # Define se é obrigatório ou opcional
            if field_name in required:
                fields[field_name] = (field_type, Field(description=field_info.get("description", "")))
            else:
                fields[field_name] = (Optional[field_type], Field(default=None, description=field_info.get("description", "")))

        # Se não houver propriedades, cria um modelo vazio
        if not fields:
            return create_model(f"{name}Input")

        return create_model(f"{name}Input", **fields)

    def _run(self, **kwargs: Any) -> Any:
        """Executa a ferramenta via ToolManager."""
        # O ToolManager espera que o nome da ferramenta seja passado.
        # Ele também lida com auditoria, contexto e execução (Local ou Docker).

        return self._tool_manager.execute_tool(
            command=self.name, # Nome da ferramenta
            context_resolver=self._context_resolver,
            audit_logger=self._audit_logger,
            tool_args=kwargs
        )

    async def _arun(self, **kwargs: Any) -> Any:
        """Execução assíncrona (Delegada para síncrona por enquanto, pois ToolManager é sync wrapper)."""
        return self._run(**kwargs)

def load_mcp_tools(tool_manager: Any, context_resolver: Any, audit_logger: Any) -> List[BaseTool]:
    """
    Carrega todas as ferramentas disponíveis no ToolManager e as converte para LangChain Tools.
    """
    langchain_tools = []

    # Itera sobre as definições de ferramentas carregadas no contexto atual
    for tool_def in tool_manager.tools_definitions:
        func_def = tool_def["function"]

        tool = MCPToolAdapter(
            name=func_def["name"],
            description=func_def["description"],
            tool_manager=tool_manager,
            schema=func_def.get("parameters", {}),
            context_resolver=context_resolver,
            audit_logger=audit_logger
        )
        langchain_tools.append(tool)

    return langchain_tools