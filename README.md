# 🌉 A-PONTE: The AIOps Platform for AWS

```text
      / \
     /   \      A-PONTE: Bridging the gap between
    /_____\     Complex Infrastructure & Human Intent.
   / \   / \
  /   \ /   \
```

> **A-PONTE** é uma plataforma de **AIOps (Artificial Intelligence for IT Operations)** que atua como um "Sistema Operacional" para a sua nuvem AWS. Ela unifica Governança, FinOps, Segurança e CI/CD em uma CLI impulsionada por uma squad de Agentes Autônomos — e foi construída para sobreviver no **Free Tier**.

![Version](https://img.shields.io/badge/version-3.0.0-blue)
![Status](https://img.shields.io/badge/Status-Production%20Ready-green)
![AWS](https://img.shields.io/badge/AWS-Free%20Tier%20Friendly-orange)
![Terraform](https://img.shields.io/badge/IaC-Terraform%20%7C%20Terragrunt-purple)
![Security](https://img.shields.io/badge/Security-OIDC%20%7C%20Checkov%20%7C%20Prowler-red)
![AI](https://img.shields.io/badge/AI-Ollama%20%7C%20RAG%20%7C%20Agents-magenta)

---

## 🧭 Índice

1. [O Que É e O Que Não É](#o-que-é-e-o-que-não-é)
2. [A Origem: O Paradoxo do Bootstrap](#a-origem-o-paradoxo-do-bootstrap)
3. [Arquitetura Cognitiva: Como a IA Pensa](#arquitetura-cognitiva-como-a-ia-pensa)
4. [Arquitetura de Execução: Cérebro e Mãos](#arquitetura-de-execução-cérebro-e-mãos)
5. [A Squad de Agentes](#a-squad-de-agentes)
6. [Segurança: As Camadas de Proteção Reais](#segurança-as-camadas-de-proteção-reais)
7. [O Gateway de IA: Estratégia Local-First](#o-gateway-de-ia-estratégia-local-first)
8. [Gestão de Contexto e Isolamento de Sessão](#gestão-de-contexto-e-isolamento-de-sessão)
9. [Tech Stack Completo](#tech-stack-completo)
10. [Pré-requisitos](#pré-requisitos)
11. [Quick Start](#quick-start)
12. [Guia de Uso dos Agentes](#guia-de-uso-dos-agentes)
13. [Comandos Rápidos](#comandos-rápidos)
14. [Documentação](#documentação)

---

## O Que É e O Que Não É

**✅ É AIOps:** Utilizamos IA Generativa para **operar, corrigir e otimizar** infraestrutura AWS. O cliente é o Engenheiro de Plataforma ou SRE. O objetivo é reduzir Toil (trabalho manual) e MTTR (Tempo de Reparo).

**❌ Não é MLOps:** Não é uma ferramenta para cientistas de dados treinarem modelos de negócio. O foco é puramente operacional e de infraestrutura.

**❌ Não é um assistente genérico de código:** O A-PONTE conhece as *suas* regras — seus ADRs, padrões de nomenclatura, restrições de segurança — e as aplica ativamente antes de sugerir qualquer código.

---

## A Origem: O Paradoxo do Bootstrap

O A-PONTE nasceu de um problema real e pouco documentado: o **Paradoxo do Bootstrap** na AWS.

> *Como criar infraestrutura segura e autenticada via OIDC sem ter infraestrutura prévia para gerenciar o estado (S3 + DynamoDB)?*

O que começou como um script para resolver esse ciclo de dependência circular evoluiu para uma plataforma completa. A restrição do **Free Tier** não foi limitação — foi restrição de design que forçou decisões arquiteturais inteligentes: estado compartilhado (1 bucket para N projetos), inferência local (Ollama), RAG offline (ChromaDB).

---

## Arquitetura Cognitiva: Projetada para Rodar numa Torradeira

A filosofia central do A-PONTE é simples: **a IA é o último recurso, não o primeiro**. Cada camada do sistema tenta resolver a tarefa sem acionar o LLM. O modelo só entra quando nenhuma outra camada conseguiu.

```
Input do Usuário
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  CAMADA 1 — SLASH COMMANDS (/ls, /tree)                         │
│  Execução direta de sistema de arquivos. Zero IA, zero latência. │
└─────────────────────────────────────────────────────────────────┘
      │ não resolveu
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  CAMADA 2 — REFLEX ENGINE (core/lib/reflex.py)                  │
│  ~55 regras Regex mapeiam linguagem natural → ferramenta.       │
│  "listar buckets", "git status", "tf plan", "ver logs"          │
│  "executar checkov", "previsão de custo", "detectar drift"...   │
│  Latência zero. Zero tokens. Zero GPU.                          │
└─────────────────────────────────────────────────────────────────┘
      │ não resolveu
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  CAMADA 3 — TOOLBELT DETERMINÍSTICO (core/lib/toolbelt.py)      │
│  Execução direta das ferramentas externas (checkov, tfsec,      │
│  tflint, trivy, infracost, gitleaks) como subprocessos.         │
│  O LLM nem sabe que isso aconteceu.                             │
└─────────────────────────────────────────────────────────────────┘
      │ reflexo falhou ou tarefa é complexa
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  CAMADA 4 — GRAPH ARCHITECT / LLM (core/agents/graph_architect) │
│  LangGraph com checkpointing SQLite. Invocado apenas quando     │
│  as camadas anteriores não conseguiram resolver.                │
│  Modelos nano (0.5b–1.5b) para tarefas rápidas,                 │
│  modelo ativo para raciocínio complexo.                         │
└─────────────────────────────────────────────────────────────────┘
      │ reflexo teve sucesso mas saída é JSON/texto bruto
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  CAMADA 5 — FEEDBACK LOOP (Humanização)                         │
│  O LLM é acionado em modo leve para interpretar a saída bruta   │
│  e gerar um resumo legível. Não repete a tarefa — apenas        │
│  traduz o resultado para o usuário.                             │
└─────────────────────────────────────────────────────────────────┘
```

### O Reflex Engine em Detalhe

O `reflex.py` cobre 8 domínios com ~55 regras — todas em português natural, com variações linguísticas:

| Domínio | Exemplos de comandos aceitos |
|:---|:---|
| **Sistema de Arquivos** | `ls`, `listar arquivos`, `cat arquivo.tf`, `tree`, `estrutura de pastas` |
| **AWS (Cloud)** | `listar buckets`, `minhas vms`, `alarmes ativos`, `status cloudtrail`, `previsao de gastos`, `whoami` |
| **Terraform** | `tf plan`, `planejar`, `tf apply`, `deploy`, `tf validate`, `formatar codigo` |
| **Git** | `git status`, `o que mudou`, `diferencas`, `historico`, `git push`, `atualizar repo` |
| **Segurança** | `executar checkov`, `run tfsec`, `run tflint`, `run trivy`, `run prowler`, `auditoria de seguranca` |
| **FinOps/Ops** | `quanto custa`, `detectar drift`, `rodar pipeline`, `diagnosticar`, `limpar cache` |
| **Pesquisa** | `pesquise sobre X`, `leia url https://...`, `gere codigo terraform para...` |
| **Conhecimento (RAG)** | `o que é X`, `me fale sobre`, `explique`, `o que são ADRs`, `como criar...` |

Comandos com parâmetros dinâmicos também são cobertos: `alarmes entre 2024-01-01 e 2024-01-31`, `logs de 2024-01-01 a 2024-02-01`, `ls infrastructure/`, `leia projects/meu-projeto/main.tf`.

### Feedback Loop: Quando o Reflexo Falha

Se uma ferramenta retornar erro (detectado por `⛔` ou `"Erro"` na saída), o sistema automaticamente aciona o LLM em **modo de análise**, não de execução. O erro já está no histórico — a IA lê o contexto e explica o que aconteceu, sem precisar repetir a tarefa.

### Memória — RAG Local (`ChromaDB`)
Banco de dados vetorial local. Armazena ADRs, documentação do projeto e histórico de sessões. A IA "lembra" das regras do *seu* negócio entre sessões — sem enviar nada para a nuvem.

### Proteção contra Alucinação de Protocolo
O Architect tem um **Hallucination Interceptor** que detecta quando o LLM sugere comandos manuais (`aws ...`, `git ...`, `terraform ...` em blocos bash) em vez de usar as ferramentas internas. Quando isso ocorre, o sistema exibe um alerta explicando a violação e pede para o usuário reformular — sem executar o comando sugerido.

---

## Arquitetura de Execução: Cérebro e Mãos

O A-PONTE separa intenção de execução usando o **Model Context Protocol (MCP)** (ADR-028):

```
┌─────────────────────┐        Tool Call (JSON)        ┌──────────────────────────┐
│   O Cérebro         │ ──────────────────────────────▶ │   As Mãos                │
│   (Agente Python)   │                                  │                          │
│                     │  ◀────────────────────────────── │  🐳 Container Docker     │
│  Decide O QUE fazer │        Resultado                 │  (Terraform, Checkov,    │
│  e QUAL ferramenta  │                                  │   TFSec, TFLint)         │
│  chamar             │                                  │                          │
│                     │                                  │  🖥️  Host Local           │
│                     │                                  │  (Git, AWS CLI com SSO)  │
└─────────────────────┘                                  └──────────────────────────┘
```

**Por que separar?** Se a IA for induzida a rodar um comando destrutivo, o dano fica contido no container. Credenciais AWS nunca ficam dentro do container permanentemente — são injetadas via variável de ambiente apenas durante a execução.

### Filosofia: O Mestre de Obras e o Construtor

- **O Cérebro (Python/Go):** Decide *o que* fazer, valida pré-condições, injeta contexto, trata erros complexos.
- **O Construtor (Terraform/HCL):** Executa a mudança de estado de forma determinística e auditável.

---

## A Squad de Agentes

O A-PONTE não opera com um único bot. São cinco agentes especializados com responsabilidades únicas (ADR-029):

### 🏗️ Architect Agent — O Engenheiro
**Comando:** `aponte architect` | **Fonte:** `core/agents/architect.py`

Interface primária com o usuário. Implementa a **Maestro Architecture** com Reflex Engine para respostas instantâneas e delega para outros agentes quando necessário. Antes de iniciar qualquer trabalho, executa um **Ritual de Iniciação** — coleta objetivo, deduz contexto (`project_name`, `environment`, `app_name`) e exige confirmação explícita. Isso garante que todo recurso criado tenha as tags corretas para rastreamento de custo (Multi-Tenant).

Para conversas sem criação de infraestrutura, aceita comandos `chat`, `duvida` ou `ola` para operar em modo livre.

### 🛡️ Auditor Agent — O Inspetor
**Comando:** `aponte audit` | **Fonte:** `core/agents/auditor.py`

Análise Estática de Segurança (SAST) em dois estágios: primeiro os scanners determinísticos (`checkov`, `tfsec`, `tflint`) — se aprovarem, o LLM nem é acionado (economia de tokens). Se houver falhas ou ambiguidade, o LLM analisa buscando falhas lógicas que ferramentas estáticas perdem.

Carrega uma **SECURITY_DIRECTIVE** hardcoded em todos os prompts: proibido `0.0.0.0/0` em portas administrativas, obrigatório `AES256` ou `aws:kms` em S3/RDS/EBS. Em modo interativo, pergunta antes de corrigir. Em modo CI/CD, quebra o pipeline silenciosamente.

### 👁️ Observer Agent — O Observador
**Comando:** `aponte ops` | **Fonte:** `core/agents/cloud_watcher.py`

SRE e FinOps. Cruza logs do CloudTrail com Alarmes do CloudWatch para diagnóstico de causa raiz. Consulta Cost Explorer e sugere otimizações concretas (ex: "Mude de gp2 para gp3"). Verifica a saúde dos containers Docker e serviços locais. Opera via `mcp_aws_reader.py` — acesso à AWS em modo read-only, sem possibilidade de mudança de estado.

### 🔴 Sentinel Agent — O Vigia
**Comando:** `aponte sentinel` | **Fonte:** `core/agents/sentinel.py`

Daemon de segurança em tempo real. Roda em background monitorando CloudTrail a cada 60 segundos. Detecta 15 tipos de eventos críticos hardcoded (Root Login, criação de usuários IAM, desativação de logs, EC2 suspeito, etc.). Usa **DynamoDB Locking** (Race to Process) para garantir que em times distribuídos apenas uma instância processe cada alerta.

**Detalhe importante:** A análise cognitiva de ameaças força `provider="ollama"` no código-fonte, independente da configuração do ambiente. Logs de segurança **nunca saem da máquina** — é uma política hardcoded, não uma configuração.

Também executa **Drift Detection** periódica (a cada 1 hora por projeto), detectando quando a infraestrutura real divergiu do código Terraform. Prefere execução via Docker sandbox quando disponível, com fallback para host.

### 🔬 Researcher Agent — O Pesquisador
**Comando:** `aponte ai train` | **Fonte:** `core/services/knowledge/researcher.py`

Engenharia de conhecimento contínuo. Faz crawling da documentação AWS/HashiCorp, compila ADRs e histórico de sessões, e gera um `aponte-ai.modelfile` para criar um modelo Ollama especializado (`aponte-ai`) com o contexto do *seu* projeto. O Architect persiste o histórico de chat ao encerrar e dispara o retreinamento automaticamente — o sistema aprende com o uso diário.

---

## A Plataforma Multi-Tenant: O Backend Terraform na AWS

A IA é a interface. O produto em si é uma **plataforma de backend Terraform multi-tenant** rodando na AWS — cada projeto é um tenant completamente isolado dos demais, compartilhando apenas a infraestrutura de controle.

### Anatomia de um Tenant

Cada projeto criado via `aponte project create` recebe um conjunto completo e isolado de recursos:

```
Conta AWS
├── INFRAESTRUTURA DE CONTROLE (compartilhada, criada no bootstrap)
│   ├── S3: a-ponte-central-tfstate-<account_id>     ← estado de todos os projetos
│   ├── DynamoDB: a-ponte-registry                   ← catálogo global de projetos
│   ├── IAM OIDC Provider                            ← federação GitHub Actions (singleton)
│   └── Permissions Boundary global
│
└── TENANT: projeto-x
    ├── S3 State Key:  projeto-x/terraform.tfstate   ← estado isolado por prefixo
    ├── DynamoDB Lock: a-ponte-lock-projeto-x         ← tabela de lock exclusiva
    ├── IAM Role:      projeto-x-github-actions-role  ← role com boundary
    ├── IAM Policy:    projeto-x-devops-policy         ← escopo restrito ao prefixo
    ├── IAM Policy:    aponte-registry-access-projeto-x ← acesso ao DynamoDB restrito por LeadingKey
    ├── S3 Buckets:    projeto-x-audit-logs-<account>
    ├── S3 Bucket:     projeto-x-config-logs-<account>
    └── (recursos de negócio do projeto...)
```

### Isolamento em 4 Camadas

**Camada 1 — Estado Terraform (`root.hcl`)**
O `root.hcl` gera o `backend.tf` dinamicamente. A chave S3 é `${TF_VAR_project_name}/terraform.tfstate` — o projeto A nunca acessa o estado do projeto B, mesmo compartilhando o bucket. A tabela de lock é por projeto (`a-ponte-lock-${project_name}`), eliminando contenção entre projetos simultâneos.

**Camada 2 — IAM: Escopo de Recursos por Nome (`policies.tf`)**
A `devops_policy` restringe todas as ações a recursos com prefixo `${project_name}-*`:
```
S3:     arn:aws:s3:::projeto-x-*
IAM:    arn:aws:iam::<account>:role/projeto-x-*
IAM:    arn:aws:iam::<account>:policy/projeto-x-*
```
O CI/CD do projeto X literalmente não consegue criar, ler ou destruir recursos do projeto Y — a política não permite.

**Camada 3 — DynamoDB: Isolamento por Partition Key (`iam.tf`)**
A política `registry_access` usa `dynamodb:LeadingKeys` com `ForAllValues:StringEquals` — o projeto só consegue ler e escrever itens onde a Partition Key (`ProjectName`) é igual ao seu próprio nome. Compartilham a tabela, mas nunca veem os dados um do outro.

**Camada 4 — Permissions Boundary: Teto Intransponível (`policies.tf`)**
Toda Role criada pelo sistema carrega um Boundary que:
- Bloqueia `iam:CreateRole` sem o mesmo Boundary anexado (impede escalação de privilégio)
- Bloqueia `iam:DeleteRolePermissionsBoundary` e `iam:PutRolePermissionsBoundary` sem replicar o Boundary (o tenant não pode remover o próprio teto)
- Bloqueia `iam:CreateUser` — apenas Roles são permitidas, nunca usuários IAM permanentes

### O que o Bootstrap Provisiona

O `aponte setup bootstrap` não é só "criar um bucket". Ele provisiona 6 módulos Terraform encadeados:

| Módulo | O que cria |
|:---|:---|
| `global` | OIDC Provider (singleton), tabela `a-ponte-registry` com PITR habilitado |
| `identity` | Role OIDC para CI/CD, Permissions Boundary, política de registry isolada, Break Glass Role + Lambda de revogação |
| `storage` | Bucket de audit logs (CloudTrail), bucket de config logs (AWS Config) — ambos com AES256, versionamento e bloqueio de acesso público |
| `observability` | CloudWatch Log Groups, CloudTrail trail, Dashboard nomeado por projeto |
| `governance` | AWS Budgets com alertas por email |
| `security` | SNS topic para alertas de segurança, integração com CloudWatch Alarms |

O Terragrunt cria o bucket S3 de estado e a tabela DynamoDB de lock automaticamente se não existirem — é a solução do Bootstrap Paradox sem nenhum script imperativo.

### Proteções de Produção no Código

O módulo `storage` tem `force_destroy = lookup(var.tags, "Environment", "") == "production" ? false : true` — buckets de produção não podem ser destruídos acidentalmente pelo Terraform, mesmo com `terraform destroy`. Os guardrails da CLI (`ALLOW_PRODUCTION_DESTROY=true`) precisam ser injetados explicitamente para contornar isso.

---

## Segurança: As Camadas de Proteção Reais

O A-PONTE tem 8 camadas de proteção ativas, não apenas declaradas:

### 1. Zero Static Keys (ADR-001)
Autenticação via **OIDC** com GitHub Actions. Tokens temporários gerados por execução. Nenhuma Access Key de longa duração em Secrets.

### 2. Permissions Boundary (ADR-002)
Todas as Roles criadas pelo sistema têm um teto máximo de permissões via **IAM Permissions Boundary** com Boundary Propagation. Mesmo com `AdministratorAccess`, não é possível criar usuários IAM sem o Boundary — prevenindo escalação de privilégio.

### 3. Versionamento Obrigatório (ADR-018)
Implementado em `core/services/versioning.py`. Nenhum agente sobrescreve um arquivo sem antes copiar o original para `.aponte-versions/<timestamp>_<filename>`. O ID do backup é registrado no DynamoDB para auditoria.

### 4. Fail Closed — Nunca Entrega Código Inseguro
Implementado em `core/tools/local_coder.py`. Se os scanners (`tfsec`, `checkov`) falharem ao executar (não apenas ao detectar problemas), o código **não é retornado**. A plataforma prefere não entregar nada a entregar infraestrutura vulnerável.

### 5. Lazy AI Safety Net
Também em `local_coder.py`. Detecta quando a IA retornou código truncado (marcadores como `// ...`, `existing code`, `rest of the code`) e aborta a operação. Heurística de tamanho: se o código gerado for menos de 50% do original sem instrução explícita de deleção, a operação é bloqueada.

### 6. Sanitização Antes da Nuvem (ADR-016)
`InputSanitizer.clean()` em `core/lib/sanitizer.py` remove AWS Access Keys (`AKIA...`), GitHub Tokens (`ghp_...`), Private Keys (PEM), senhas em connection strings e Google API Keys de qualquer prompt antes de enviá-lo para provedores externos (OpenRouter/Gemini).

### 7. Isolamento de Contexto (ADR-027)
O contexto do projeto (`project_name`) é isolado por sessão via `~/.aponte/sessions/<user>.<pid>`. Múltiplos terminais do mesmo usuário não interferem entre si. O menu sempre inicia em estado neutro (`home`) — impossível disparar um `destroy` acidentalmente no projeto errado.

### 8. Break Glass com Expiração Server-Side (ADR-007)
Acesso de emergência via Role IAM com MFA obrigatório. A revogação é agendada no **AWS EventBridge Scheduler** — mesmo que a máquina do operador seja desligada, o acesso expira automaticamente no lado da AWS.

---

## O Gateway de IA: Ollama Local + OpenRouter

O A-PONTE tem exatamente dois provedores de IA, nada mais:

```
AI_PROVIDER=ollama (padrão)          AI_PROVIDER=openrouter  (ou "google" — mesmo backend)
       │                                      │
       ▼                                      ▼
 LocalProvider                         CloudProvider
 (core/services/ollama.py)             (core/services/openrouter.py)
       │                                      │
       ├─ Modelo: aponte-ai (treinado)        ├─ Endpoint: openrouter.ai/api/v1/chat/completions
       ├─ Fallback: qwen2.5-coder:1.5b        ├─ Modelo default: gemini-2.0-flash-lite:free
       ├─ Download automático se ausente       ├─ Exponential backoff + jitter (2^n segundos)
       ├─ Checagem de versão (exige v0.3+)     ├─ Sanitização de credenciais antes do envio
       └─ Ciclo de vida Just-in-Time           └─ Rate limit: 3 tentativas com backoff
          (inicia sob demanda, para após uso)
```

**Detalhe importante:** o `.env.example` define `AI_PROVIDER=google` e `GOOGLE_API_KEY`, mas não existe integração direta com a API do Google. O `llm_gateway.py` trata `"google"` e `"openrouter"` como sinônimos do mesmo `CloudProvider` — ambos rotreiam para `openrouter.py`, que envia o request para o endpoint do OpenRouter com `OPENROUTER_API_KEY`. O Gemini é acessado *através* do OpenRouter, não diretamente.

A estratégia **Local-First** não é apenas sobre privacidade — é sobre custo zero. O modelo default do OpenRouter é `gemini-2.0-flash-lite:free`. Mesmo no modo cloud, o custo permanece zero.

Dois outros detalhes do código que valem mencionar: o gateway resolve automaticamente modelos "nano" (`qwen2.5:0.5b`, `llama3.2:1b`) para tarefas rápidas quando `size="nano"` é solicitado — economizando GPU onde não é necessário. E o modelo `aponte-ai` recebe tratamento especial: mensagens com `role="system"` são convertidas para `role="user"` antes de enviar ao Ollama, preservando a identidade do Modelfile treinado que a API sobrescreveria sem esse fix.

---

## Gestão de Contexto e Isolamento de Sessão

O contexto do projeto segue uma **hierarquia estrita** de leitura (SSOT):

```
1. TF_VAR_project_name (variável de ambiente) — Prioridade máxima
2. ~/.aponte/sessions/<user>.<session_pid>    — Persistência por sessão
3. "home"                                    — Estado neutro (fallback)
```

Todos os logs carregam o contexto do projeto injetado automaticamente via `ContextFilter`. O formato de log é `[timestamp] [LEVEL] [project_name] módulo: mensagem` — rastreabilidade total de qual projeto gerou qual evento.

O `aponte install` cria um wrapper no perfil do seu shell que é **idempotente**: remove configurações legadas antes de escrever a nova, suporta bash, zsh e PowerShell, e detecta automaticamente ambientes mistos (WSL + Windows).

---

## Tech Stack Completo

| Componente | Tecnologia | Por Quê |
|:---|:---|:---|
| **CLI** | Go + Cobra | Binário estático, startup instantâneo, distribuição simples |
| **Agentes** | Python + Rich | Ecossistema de IA, TUI, agilidade em lógica complexa |
| **IaC** | Terraform + Terragrunt | Estado compartilhado, backend automático, DRY |
| **IA Local** | Ollama | Privacidade total, custo zero, offline |
| **IA Cloud** | OpenRouter (Gemini free) | Escalabilidade quando o hardware local não basta |
| **Memória** | ChromaDB | RAG offline, portabilidade via Git |
| **Sandbox** | Docker (mcp-terraform) | Isolamento de execução, versões reprodutíveis |
| **Estado** | S3 + DynamoDB | Estado compartilhado multi-projeto (1 bucket, N prefixos) |
| **Segurança** | Checkov, TFSec, TFLint, Gitleaks, Trivy, Prowler | Cobertura completa: sintaxe, segurança, compliance |
| **CI/CD** | GitHub Actions + OIDC | Zero static keys |
| **Auditoria** | DynamoDB (`a-ponte-ai-history`) | Memória compartilhada de incidentes entre analistas |

---

## Pré-requisitos

A CLI atua como orquestrador híbrido. Para uso completo:

1. **Docker (Engine + Compose)** — Essencial. Roda o sandbox Terraform e o banco vetorial.
2. **Python 3.10+** — Essencial. Executa os agentes de IA e o menu interativo.
3. **Git CLI** — Para clonar repositórios.
4. **GitHub CLI (`gh`)** — Para configurar CI/CD e Secrets.
5. **Go (Golang)** — Para compilar a CLI nativa `aponte` (necessário apenas uma vez).

**Instalação das dependências (Ubuntu/Debian/WSL):**
```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin python3 python3-pip python3-venv git golang-go
# GitHub CLI: https://cli.github.com/manual/installation
```

---

## Quick Start

```bash
# 1. Compilar e instalar a CLI globalmente
go build -o bin/aponte ./cli
./bin/aponte install
source ~/.bashrc  # ou ~/.zshrc

# 2. Instalar dependências Python
aponte setup python

# 3. Instalar Ollama e baixar o modelo base
aponte setup ollama
ollama pull qwen2.5-coder:1.5b

# 4. (Opcional) Treinar o cérebro especializado
aponte ai train

# 5. Subir a infraestrutura local (Docker)
aponte infra up

# 6. Provisionar infraestrutura base na AWS (S3 state + DynamoDB lock)
aponte setup bootstrap

# 7. Iniciar o Arquiteto Virtual
aponte architect
```

---

## Guia de Uso dos Agentes

### 🏗️ Architect Agent (`aponte architect`)

O Arquiteto opera em dois modos:

**Modo Construtor (padrão):** Exige o Ritual de Iniciação antes de criar qualquer recurso. Ele deduz e confirma 4 variáveis (`project_name`, `environment`, `app_name`, `infra_type`) para garantir tags de custo corretas em todo recurso criado (Multi-Tenant).

**Modo Livre:** Para dúvidas de AWS ou discussões de arquitetura sem criação de infraestrutura, inicie com `chat`, `duvida` ou `ola`.

### 🛡️ Sentinel Agent (`aponte sentinel`)

Deixe rodando em uma aba separada. Ele monitora autonomamente:
- Eventos críticos no CloudTrail a cada 60 segundos
- Drift de infraestrutura a cada hora por projeto
- Executa auto-auditoria de segurança periódica no seu código

### 🚑 Doctor (`aponte doctor`)

O botão de pânico. O `terraform apply` quebrou? O container não sobe? O Doctor lê o `system.log`, entende o erro, busca na memória compartilhada (DynamoDB) se esse erro já ocorreu antes e propõe a correção mais rápida.

### 🕵️ Auditor Agent (`aponte audit`)

**Modo Interativo:** Analisa arquivo por arquivo. Se achar um problema, explica e pergunta: *"Posso corrigir para você?"*. Se sim, reescreve o código e versiona o original automaticamente.

**Modo CI/CD:** `aponte audit --check` — roda silencioso e quebra o pipeline em caso de falha.

---

## Comandos Rápidos

| Ação | Comando | Descrição |
|:---|:---|:---|
| **Instalar** | `aponte install` | Configura o acesso global à CLI |
| **Conversar** | `aponte architect` | Inicia o Arquiteto Virtual |
| **Vigiar** | `aponte sentinel` | Inicia o Sentinela (Daemon) |
| **Auditar** | `aponte audit` | Verificação de segurança com auto-fix |
| **Diagnosticar** | `aponte doctor` | Diagnostica erros do sistema |
| **Observar** | `aponte ops` | SRE: logs, custos, saúde |
| **Validar** | `aponte ops pipeline` | Esteira completa de qualidade |
| **Subir infra local** | `aponte infra up` | Inicia containers Docker |
| **Bootstrap AWS** | `aponte setup bootstrap` | Provisiona S3 state + DynamoDB |
| **Treinar IA** | `aponte ai train` | Cria/atualiza o cérebro `aponte-ai` |
| **Listar projetos** | `aponte project list` | Lista projetos no registro DynamoDB |
| **Trocar projeto** | `aponte project switch <nome>` | Muda o contexto ativo |

---

## Documentação

- [🤖 Agentes (Squad)](docs/AGENTS.md) — Detalhes sobre Architect, Auditor, Sentinel e Observer
- [🛡️ Segurança (Safety)](docs/SAFETY.md) — Camadas de proteção, versionamento e auditoria
- [🛠️ Ferramentas (Tools)](docs/TOOLS.md) — Local Coder, MCP e AWS Reader
- [🎭 Manifesto](docs/MANIFESTO.md) — A identidade e os valores da IA
- [📝 ADRs](docs/adrs/ADR.md) — 29 Registros de Decisão Arquitetural comentados

---

> *"Não sou um chatbot passivo. Sou opinativa, protetora e educativa. Se você me pedir para abrir a porta 22 para o mundo, eu não direi apenas 'Acesso Negado'. Eu explicarei o risco, ensinarei o caminho correto via SSM e perguntarei se posso configurar isso para você."*
> — Manifesto do Operador A-PONTE
