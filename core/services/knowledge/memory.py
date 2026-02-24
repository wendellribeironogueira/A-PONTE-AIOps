import json
import re
import time
from datetime import datetime
from typing import Optional

from botocore.config import Config

from core.lib import aws
from core.lib import utils as common


def fetch_similar_history(error_msg: str) -> str:
    """
    RAG Lite: Busca no histórico global (DynamoDB) por erros similares.
    Usa Scan limitado para obter contexto recente de qualquer projeto (Shared Brain).
    """
    context_memory = ""
    try:
        retry_config = Config(retries={"max_attempts": 10, "mode": "adaptive"})
        dynamodb = aws.get_session().resource("dynamodb", config=retry_config)
        table = dynamodb.Table(aws.AI_HISTORY_TABLE)

        # MELHORIA TÉCNICA: Scan Reverso (Index Forward=False) não é suportado nativamente em Scan,
        # mas podemos mitigar lendo apenas segmentos se a tabela for grande.
        response = table.scan(
            Limit=50,
            ProjectionExpression="ProjectName, ErrorSnippet, Analysis, #ts",
            ExpressionAttributeNames={"#ts": "Timestamp"},
        )
        items = response.get("Items", [])

        # Ordena por timestamp (memória recente primeiro)
        items.sort(key=lambda x: x.get("Timestamp", ""), reverse=True)

        relevant_items = []
        # Tokenização simples para match de palavras-chave
        current_words = set(re.findall(r"\w+", error_msg.lower()))

        for item in items:
            past_error = item.get("ErrorSnippet", "").lower()
            past_words = set(re.findall(r"\w+", past_error))

            # Interseção: palavras > 4 letras para evitar conectivos genéricos
            common_words = {
                w for w in current_words.intersection(past_words) if len(w) > 4
            }

            # Se houver similaridade semântica básica (pelo menos 2 palavras técnicas iguais)
            if len(common_words) >= 2:
                analysis = item.get("Analysis", "")
                # Resume a análise para economizar tokens no prompt
                summary = " ".join(analysis.split())[:300]
                relevant_items.append(
                    f"- [Projeto: {item.get('ProjectName')}] Erro: ...{past_error[:50]}... -> Dica Passada: {summary}..."
                )

        if relevant_items:
            # Pega top 3 mais recentes
            context_memory = (
                "🧠 MEMÓRIA COMPARTILHADA (Erros Similares em Outros Projetos):\n"
                + "\n".join(relevant_items[:3])
                + "\n"
            )

    except Exception as e:
        # Silencia erro se a tabela não existir (primeira execução)
        if "ResourceNotFoundException" in str(e):
            return ""
        common.log_warning(f"Falha não-bloqueante no RAG Lite (Histórico): {e}")

    # FALLBACK: Memória Local (Offline Mode)
    # Se o DynamoDB falhou ou não retornou nada, tenta ler do arquivo local
    if not context_memory:
        try:
            history_file = common.get_project_root() / "logs" / "ai_history.json"
            if history_file.exists():
                # Lê as últimas 50 entradas para performance
                lines = history_file.read_text(encoding="utf-8").strip().split('\n')[-50:]
                local_items = []
                current_words = set(re.findall(r"\w+", error_msg.lower()))

                for line in reversed(lines): # Mais recentes primeiro
                    try:
                        entry = json.loads(line)
                        past_error = entry.get("error_snippet", "").lower()
                        past_words = set(re.findall(r"\w+", past_error))
                        common_words = {w for w in current_words.intersection(past_words) if len(w) > 4}

                        if len(common_words) >= 2:
                            summary = " ".join(entry.get("analysis", "").split())[:300]
                            local_items.append(f"- [Local: {entry.get('project')}] Erro: ...{past_error[:50]}... -> Dica: {summary}...")
                    except json.JSONDecodeError:
                        continue

                if local_items:
                    context_memory = "🧠 MEMÓRIA LOCAL (Offline Cache):\n" + "\n".join(local_items[:3]) + "\n"
        except Exception:
            pass

    return context_memory


def save_diagnosis(project_context: str, error: str, analysis: str):
    """Salva o diagnóstico no DynamoDB Central (Multi-Tenant)."""
    timestamp = datetime.now().isoformat()
    # TTL: Expira em 90 dias (Unix Timestamp) para evitar custos infinitos
    ttl = int(time.time() + (90 * 24 * 60 * 60))

    retry_config = Config(retries={"max_attempts": 10, "mode": "adaptive"})

    try:
        dynamodb = aws.get_session().resource("dynamodb", config=retry_config)
        table = dynamodb.Table(aws.AI_HISTORY_TABLE)

        item = {
            "ProjectName": project_context,
            "Timestamp": timestamp,
            "ExpirationTime": ttl,
            "ErrorSnippet": error[:200],
            "Analysis": analysis,
            "Author": aws.get_current_user(),
        }

        table.put_item(Item=item)
        common.log_success(
            f"Diagnóstico salvo na memória central (DynamoDB): {project_context}"
        )

    except Exception as e:
        # Auto-healing: Se a tabela não existir, cria e tenta de novo
        if "ResourceNotFoundException" in str(e):
            common.log_warning(
                "Tabela de memória da IA não encontrada. Criando agora..."
            )
            if aws.create_ai_history_table():
                try:
                    aws.get_session().resource("dynamodb", config=retry_config).Table(
                        aws.AI_HISTORY_TABLE
                    ).put_item(Item=item)
                    common.log_success(
                        f"Diagnóstico salvo na memória central (DynamoDB): {project_context}"
                    )
                    return
                except Exception:
                    pass

        common.log_error(f"Falha ao salvar histórico da IA no DynamoDB: {e}")
        # Fallback local
        history_file = common.get_project_root() / "logs" / "ai_history.json"
        entry = {
            "timestamp": timestamp,
            "project": project_context,
            "error_snippet": error[:200],
            "analysis": analysis,
            "author": "local_fallback",
        }
        try:
            with open(history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
