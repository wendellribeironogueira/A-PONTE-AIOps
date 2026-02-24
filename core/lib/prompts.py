from core.lib import utils as common


class PromptLoader:
    """
    Gerencia o carregamento e renderização de templates de prompt (Markdown).
    """

    def __init__(self, prompts_dir="core/lib"):
        self.root = common.get_project_root()
        self.prompts_path = self.root / prompts_dir

    def load(self, template_name: str, **kwargs) -> str:
        """
        Carrega um arquivo .md e injeta as variáveis de contexto (f-string style).

        Args:
            template_name: Nome do arquivo (ex: 'architect_system') sem extensão.
            **kwargs: Variáveis para substituição no template ({var}).
        """
        target_file = self.prompts_path / f"{template_name}.md"

        if not target_file.exists():
            # Fallback para tentar encontrar em core/domain/prompts/v3 se não estiver em core/lib
            fallback_path = (
                self.root / "core" / "domain" / "prompts" / "v3" / f"{template_name}.md"
            )
            if fallback_path.exists():
                target_file = fallback_path
            else:
                return f"Erro: Template de prompt '{template_name}' não encontrado em {self.prompts_path}"

        try:
            content = target_file.read_text(encoding="utf-8")
            # Realiza a substituição segura das variáveis
            return content.format(**kwargs)
        except KeyError as e:
            return f"Erro de Renderização de Prompt: Variável ausente {e}"
        except Exception as e:
            return f"Erro ao carregar prompt: {e}"
