# 🛠️ Catálogo de Ferramentas MCP (Model Context Protocol)

Este documento descreve as ferramentas disponíveis para os Agentes de IA da plataforma A-PONTE.
Estas ferramentas são expostas via servidores MCP (`core/services/mcp_*.py`) e executadas em ambientes isolados (Sandbox ou Host).

---

## 🏗️ Terraform Agent (`mcp-terraform`)
**Ambiente:** Docker Container (`mcp-terraform`)
**Foco:** Infraestrutura como Código (IaC), Deploy e Validação.

| Ferramenta | Descrição | Parâmetros Chave |
| :--- | :--- | :--- |
| `tf_plan` | Executa `terragrunt plan`. Gera um plano de execução (Dry Run). | `project_name`, `environment`, `app_name` |
| `tf_apply` | Executa `terragrunt apply`. Aplica mudanças na AWS. | `project_name`, `authorization="AUTORIZADO"` |
| `tf_rollback` | Executa `terragrunt destroy`. Remove infraestrutura. | `project_name`, `confirmation="ROLLBACK_CONFIRMED"` |
| `tf_scan` | Roda bateria de segurança (Checkov, TFSec, TFLint). | `project_name` |
| `ping` | Healthcheck do servidor. | - |

---

## ☁️ AWS Reader Agent (`mcp-aws-reader`)
**Ambiente:** Host (Local)
**Foco:** Leitura de estado da nuvem, Observabilidade e FinOps.
**Segurança:** Read-Only (Boto3).

| Ferramenta | Descrição | Parâmetros Chave |
| :--- | :--- | :--- |
| `aws_list_resources` | Lista recursos AWS e suas tags (Resource Groups). | `resource_type_filters` |
| `aws_get_cloudwatch_alarms` | Lista alarmes em estado ALARM. | `state` |
| `aws_get_cost_forecast` | Previsão de custos para o mês atual (Cost Explorer). | - |
| `aws_check_cloudtrail` | Verifica status das trilhas de auditoria. | - |
| `aws_list_log_groups` | Lista grupos de logs do CloudWatch. | `name_prefix` |
| `aws_filter_log_events` | Busca logs com filtro de texto. | `log_group_name`, `filter_pattern` |
| `aws_simulate_principal_policy` | Simula permissões IAM (Policy Simulator). | `policy_source_arn`, `action_names` |

---

## 🐙 Git Agent (`mcp-git`)
**Ambiente:** Host (Local)
**Foco:** Gestão de código fonte e versionamento.

| Ferramenta | Descrição | Parâmetros Chave |
| :--- | :--- | :--- |
| `git_clone` | Clona repositórios remotos. | `repo_url`, `destination` |
| `git_commit_push` | Realiza add, commit e push. | `repo_path`, `message` |
| `git_status` | Verifica estado do repositório. | `repo_path` |
| `git_log` | Lê histórico de commits. | `repo_path` |
| `git_checkout` | Alterna branches ou tags (Rollback de código). | `repo_path`, `target` |

---

## 🧠 Research Agent (`mcp-research`)
**Ambiente:** Host (Local) + Container (Crawl4AI)
**Foco:** Busca na web e ingestão de conhecimento.

| Ferramenta | Descrição | Parâmetros Chave |
| :--- | :--- | :--- |
| `web_search` | Pesquisa no DuckDuckGo. | `query` |
| `read_url` | Lê conteúdo de URL (Markdown limpo via Crawl4AI). | `url` |
| `get_sources_list` | Lê lista de fontes de aprendizado. | - |

---

## ⚙️ Ops Agent (`mcp-ops`)
**Ambiente:** Host (Local)
**Foco:** Operações de sistema e manutenção da IA.

| Ferramenta | Descrição | Parâmetros Chave |
| :--- | :--- | :--- |
| `diagnose_system` | Executa o AI Doctor para analisar logs de erro. | `project_name` |
| `train_knowledge_base` | Re-treina o modelo da IA com novos documentos. | - |
| `ingest_sources` | Baixa e processa URLs da lista de fontes. | - |

---

## 🛡️ Arquitetura de Segurança

1.  **Isolamento:** Ferramentas destrutivas (`tf_apply`) rodam em container Docker isolado.
2.  **Confirmação:** Ações críticas exigem tokens de confirmação explícitos (`AUTORIZADO`).
3.  **Escopo:** Ferramentas de Git validam se o caminho está dentro do projeto (`validate_path`).
4.  **Sanitização:** O Research Agent bloqueia termos maliciosos/hacking.
```
