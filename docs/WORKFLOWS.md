# 🌊 Workflows e Melhorias da Plataforma A-PONTE

Este documento consolida os fluxos de trabalho (workflows) operacionais da plataforma e registra as melhorias recentes implementadas na arquitetura de agentes e automação.

## 🚀 Workflows Principais

### 1. Bootstrap (Inicialização)

**Comando:** `aponte setup bootstrap`
**Objetivo:** Criar a "espinha dorsal" da plataforma (S3 Backend, DynamoDB Lock, GitHub Repo).
**Fluxo:**

1.  Verifica credenciais AWS e GitHub.
2.  Cria Bucket S3 e Tabela DynamoDB (se não existirem).
3.  Gera `backend.tf` dinamicamente.
4.  Executa `terraform apply` para infraestrutura base (IAM, Buckets de Log).
5.  Registra o projeto `a-ponte` no DynamoDB Registry.
6.  Inicializa repositório Git e configura Secrets/Variables no GitHub.
7.  Exibe resumo visual dos recursos criados.

### 2. Ciclo de Desenvolvimento (IaC)

**Comandos:** `aponte project create` -> `aponte tf plan` -> (`aponte deploy project` OU `aponte git push`)
**Objetivo:** Criar e manter projetos de infraestrutura.
**Fluxo:**

1.  **Criação (Scaffold):** O Arquiteto usa `aponte project scaffold` para gerar a estrutura de pastas, `versions.tf` e `backend.tf` baseados em templates (Cookiecutter-like), garantindo padronização desde o dia 0.
2.  **Planejamento (Sandbox):** O comando `aponte tf plan` sobe o container `mcp-terraform`, monta o volume do projeto e executa `terragrunt plan` em ambiente isolado.
3.  **Aplicação (Decisão de Ambiente):**
    *   **Dev/Staging (Local):** O comando `aponte deploy project` executa o deploy localmente via container para feedback rápido.
    *   **Produção (GitOps):** O código deve ser commitado e enviado (`aponte git push`). O GitHub Actions (configurado no Bootstrap) detecta a mudança e executa o `terraform apply` com aprovação manual.
4.  **Backend:** O arquivo `backend.tf` é gerado automaticamente em tempo de execução para garantir o apontamento correto para o S3 central.

### 3. Segurança e Auditoria

**Comandos:** `aponte audit`, `aponte security prowler`
**Objetivo:** Garantir conformidade e segurança.
**Fluxo:**

1.  **Refatoração:** Executa `aponte tools refactor` para limpar código (fmt/lint) antes da análise.
2.  **Análise Estática:** Roda `tfsec`, `checkov`, `trivy`.
3.  **Análise IA:** O `AuditorAgent` analisa o código em busca de falhas lógicas e sugere correções.

### 4. Observabilidade e Custos

**Comandos:** `aponte observer`, `aponte cost estimate`
**Objetivo:** Monitorar saúde e gastos.
**Fluxo:**

1.  **Watch:** O `ObserverAgent` (`aponte observer`) usa o MCP AWS para consultar CloudWatch e Cost Explorer de forma segura (Read-Only).
2.  **Cost:** Usa Infracost para estimar impacto financeiro antes do deploy.

### 5. Cura e Manutenção (Healing)

**Comandos:** `aponte system heal`, `aponte doctor`
**Objetivo:** Recuperar o ambiente de falhas.
**Fluxo:**

1.  **Doctor:** IA analisa logs e sugere diagnósticos.
2.  **Heal:** Limpeza profunda de caches (`.terraform`, `.terragrunt-cache`) e reinicialização do backend.

### 6. Alinhamento de Repositórios (Git Audit)

**Comando:** `aponte audit --git`
**Objetivo:** Garantir que repositórios externos (App ou Infra) sigam os padrões da plataforma (ADRs).
**Cenário:** Importação de um repositório legado (ex: `terraform-aws`) que não exporta parâmetros SSM.
**Cenário App:** Análise de um repositório de aplicação (Python/Node/Java) para gerar infraestrutura correspondente.
**Fluxo:**

1.  **Análise:** A IA lê o código (Dockerfile, requirements.txt) e detecta a Stack Tecnológica.
2.  **Geração (App -> Infra):** Se for um App, a IA gera o código Terraform (ECS, RDS, S3) necessário para suportá-lo.
3.  **Auto-Fix (Infra):** Se for Infra, detecta violações (ex: falta de SSM, tags incorretas) e propõe correções.
4.  **Persistência:** O código gerado/corrigido é salvo em `.aponte-versions/` ou commitado e enviado de volta ao GitHub.

---

## ✨ Melhorias Recentes (Changelog)

### 🤖 Evolução do Sentinel Agent (O Robô)

O agente autônomo (`core/agents/sentinel.py`) recebeu novas capacidades:

- **💰 FinOps Agent:** Monitora orçamentos AWS e alerta se o consumo projetado exceder 80%.
 - **🕵️ Drift Hunter:** Executa verificações periódicas (`aponte drift detect`) para detectar alterações manuais (ClickOps).
- **🧹 Janitor Agent:** Limpa artefatos temporários e organiza backups automaticamente.
- **💥 Chaos Agent:** Injeta falhas simuladas em ambientes não-produtivos para testar resiliência.
- **🏥 Health Check:** Monitora logs locais e anomalias na nuvem (via Observer) a cada ciclo.
- **Robustez:** Adição de timeouts em todas as chamadas de sistema para evitar travamentos.
 - **🧠 Researcher (Knowledge):** Novo serviço desacoplado que navega na web (Crawl4AI), ingere documentação e treina o modelo (`aponte ai train`) periodicamente.

### 🧠 Otimização de IA (Pirâmide de Refatoração)

Implementação da estratégia de "IA Híbrida" para economia de tokens e performance:

 - **Novo Comando:** `aponte tools refactor`.
- **Funcionamento:** Aplica correções determinísticas (`terraform fmt`, `black`, `tflint --fix`) _antes_ de acionar a IA Generativa.
- **Benefício:** O código chega limpo para o LLM, reduzindo alucinações e custo computacional.

### 🛠️ Hardening do Setup

Melhorias no Bootstrap:

- **Contexto:** Correção do gerenciamento de contexto (`.current_project`) para evitar que o usuário fique "preso" no projeto de bootstrap.
- **UX:** Adição de painel de resumo visual ao final da execução.

### 🔧 Core & CLI


- **Cloud Watcher:** Correção de bugs (função `fetch_cloud_errors` ausente) e adição de timeouts.
