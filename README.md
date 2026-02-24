# 🌉 A-PONTE: The AIOps Platform for AWS

```text
      / \
     /   \      A-PONTE: Bridging the gap between
    /_____\     Complex Infrastructure & Human Intent.
   / \   / \
  /   \ /   \
```

> **A-PONTE** é uma plataforma de **AIOps (Artificial Intelligence for IT Operations)** e **Engenharia de Plataforma**. Ela atua como um "Sistema Operacional" para sua nuvem AWS, unificando Governança, FinOps, Segurança e CI/CD em uma interface de linha de comando (CLI) impulsionada por Agentes Autônomos.

![Version](https://img.shields.io/badge/version-3.0.0-blue)
![Status](https://img.shields.io/badge/Status-Production%20Ready-green)
![AWS](https://img.shields.io/badge/AWS-Free%20Tier%20Friendly-orange)
![Terraform](https://img.shields.io/badge/IaC-Terraform%20%7C%20Terragrunt-purple)
![Security](https://img.shields.io/badge/Security-OIDC%20%7C%20Checkov%20%7C%20Prowler-red)
![AI](https://img.shields.io/badge/AI-Ollama%20%7C%20RAG%20%7C%20Agents-magenta)

---

## 🌟 O Que A-PONTE Faz? (Capabilities)

A plataforma resolve a complexidade de operar na nuvem através de 4 pilares fundamentais:

### 1. 🏗️ Engenharia & Provisionamento (Build)
*   **Multi-Tenant Nativo:** Gerencia múltiplos projetos isolados (`projects/`) com estados remotos (S3/DynamoDB) segregados automaticamente.
*   **IaC Abstraído:** Gera, valida e aplica código **Terraform** e **Terragrunt** seguindo as melhores práticas (AWS Well-Architected).
*   **Self-Healing:** O Agente `Doctor` diagnostica erros de deploy e sugere correções baseadas em logs e histórico.

### 2. 🛡️ Segurança & Governança (Secure)
*   **Zero Static Keys:** Autenticação via **OIDC (OpenID Connect)** com GitHub Actions. Adeus, Access Keys vazadas!
*   **Guardrails Ativos:** Scanners de segurança (Checkov, TFSec, Trivy, Gitleaks) rodam antes de qualquer commit.
*   **Sentinel Daemon:** Um agente que roda em background monitorando o CloudTrail em tempo real para detectar ameaças e Drift.
*   **Compliance:** Auditoria contínua com **Prowler** (CIS Benchmarks, GDPR, HIPAA).

### 3. 👁️ Observabilidade & FinOps (Observe)
*   **Custo sob Controle:** Estimativa de custos (Infracost) antes do deploy e previsão de gastos (Cost Explorer) via chat.
*   **Logs Centralizados:** Agregação de logs do CloudWatch e auditoria de ações da IA no DynamoDB.
*   **Drift Detection:** Alerta quando a infraestrutura real diverge do código.

### 4. 🤖 Inteligência & Automação (Automate)
*   **Agentes Especializados:** Uma squad de robôs (Arquiteto, Auditor, Sentinela) que trabalham juntos.
*   **RAG (Memória):** A IA "lê" sua documentação (`docs/`) e ADRs, aprendendo as regras do *seu* negócio.
*   **CI/CD Pipeline:** Workflows de GitHub Actions prontos para validação, teste e deploy automatizado.

### 🧠 Conceito: AIOps vs MLOps

É importante distinguir o propósito da plataforma:

*   **✅ É AIOps:** Utilizamos IA Generativa para **operar, corrigir e otimizar** a infraestrutura. O "cliente" é o Engenheiro de Plataforma ou SRE. O objetivo é reduzir o *Toil* (trabalho manual) e o MTTR (Tempo de Reparo).
*   **❌ Não é MLOps:** Não é uma ferramenta para cientistas de dados treinarem modelos de negócio (ex: previsão de vendas). O foco é puramente Operacional e de Infraestrutura.

### 💡 A Origem (Do Script à Plataforma)

A-PONTE nasceu da necessidade real de resolver o **"Paradoxo do Bootstrap"** na AWS: *Como criar infraestrutura segura e autenticada (OIDC) sem ter infraestrutura prévia para gerenciar o estado?*

O que começou como um script Python para gerenciar credenciais evoluiu para um ecossistema completo. Diferente de projetos de portfólio comuns, este é um projeto de **Engenharia de Verdade**, projetado para:
1.  **Sobreviver no Free Tier:** Arquitetura otimizada para custo zero/baixo.
2.  **Resolver Problemas Reais:** Multi-tenancy, Segurança, Observabilidade.
3.  **Ensinar:** Uma plataforma que eleva o nível do operador.

---

## 📚 Documentação

A documentação técnica foi restaurada e organizada para facilitar a navegação:

*   🚀 Guia de Onboarding: **Comece aqui!** Glossário completo de ferramentas, agentes e scripts.
*   [🤖 Agentes (Squad)](docs/AGENTS.md): Detalhes sobre Architect, Auditor, Sentinel e Observer.
*   [🛠️ Ferramentas (Tools)](docs/TOOLS.md): Funcionamento do Local Coder, MCP e AWS Reader.
*   [🛡️ Segurança (Safety)](docs/SAFETY.md): Mecanismos de defesa, versionamento e auditoria.
*   [🎭 Manifesto](docs/MANIFESTO.md): A identidade e os valores da IA.
*   [📝 ADRs](docs/adrs/ADR.md): Registros de Decisão Arquitetural.

## 🏗️ Arquitetura & Infraestrutura Local

O A-PONTE não é apenas um script; é uma plataforma de orquestração composta por microsserviços locais, desenhada para segurança e eficiência.

### 🧠 Arquitetura Cognitiva (Como a IA Pensa)

Utilizamos uma abordagem híbrida **System 1 / System 2** para otimizar recursos e latência:

1.  **System 1 (Reflex Engine):**
    *   **O que é:** Motor de Regex de alta performance (`core/lib/reflex.py`).
    *   **Função:** Intercepta comandos diretos (`ver logs`, `listar buckets`) e executa instantaneamente.
    *   **Por que usamos?** **Latência Zero**. Economiza GPU/CPU e evita alucinações em tarefas determinísticas.

2.  **System 2 (LLM Reasoning):**
    *   **O que é:** O Modelo de Linguagem (Ollama/Gemini).
    *   **Função:** Entra em ação para tarefas complexas, planejamento e geração de código.
    *   **Por que usamos?** Para lidar com ambiguidade e criatividade (`desenhe uma arquitetura`).

3.  **Memória (RAG):**
    *   **O que é:** Banco de dados vetorial (**ChromaDB**).
    *   **Função:** Armazena documentação (`docs/`), ADRs e histórico de sessões.
    *   **Por que usamos?** Para que a IA conheça as regras do *seu* projeto ("Contexto Infinito").

---

### 🛡️ Arquitetura de Execução (Protocolo MCP)

Para segurança, separamos o "Cérebro" das "Mãos" usando o **Model Context Protocol (MCP)**:

*   **O Cérebro (Host):** O Agente Python roda no seu terminal. Ele decide *o que* fazer.
*   **As Mãos (Docker Sandbox):** Ferramentas críticas (`terraform`, `checkov`) rodam isoladas em containers.
    *   **Por que usamos Docker?** Se a IA tentar rodar um comando destrutivo, o dano é contido no container. Garante que todos usem as mesmas versões de ferramentas.

---

### 🐳 O Ecossistema (Tech Stack)

Por que escolhemos estas ferramentas?

| Serviço | Função | Descrição |
| :--- | :--- | :--- |
| **🧠 Ollama** | *Inference Server* | **Privacidade & Custo.** Executa modelos LLM (ex: `qwen2.5-coder`) localmente. Seus dados nunca saem da máquina. |
| **🏭 MCP Sandbox** | *Execution Engine* | **Segurança & Reprodutibilidade.** Container Docker com Terraform, Terragrunt, Checkov, Prowler e Linters pré-instalados. |
| **📚 ChromaDB** | *Vector Database* | **Memória de Longo Prazo.** Banco vetorial local para RAG. Permite que a IA "lembre" de documentos e regras do projeto. |
| **🐍 Python (Rich)** | *Orchestrator* | **UX & Glue.** Gerencia a lógica de agentes, reflexos e fornece uma interface de terminal (TUI) interativa. |
| **☁️ Hybrid AI** | *Cloud Brain* | **Escalabilidade.** Suporte opcional a Gemini/OpenAI para raciocínio complexo quando necessário. |

## 📋 Pré-requisitos (Kit de Sobrevivência)

A CLI do A-PONTE atua como um orquestrador híbrido. Para utilizá-la no estado atual, você precisa das seguintes ferramentas instaladas no seu sistema:

1.  **Docker (Engine + Compose):** Essencial. Roda o sandbox de Terraform e banco de dados.
2.  **Python 3.10+:** Essencial. Executa o cérebro da IA e o menu interativo.
3.  **Git CLI:** Necessário para clonar repositórios.
4.  **GitHub CLI (`gh`):** Necessário para configurar CI/CD e Secrets.
5.  **Go (Golang):** Necessário para compilar a CLI nativa `aponte`.

**Instalação das dependências (Ubuntu/Debian/WSL):**
```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin python3 python3-pip python3-venv git golang-go
# Instale o GitHub CLI: https://cli.github.com/manual/installation
```

## �🚀 Quick Start

```bash
# 1. Iniciar a infraestrutura de suporte (Docker)
aponte infra up

# 2. Baixar o modelo neural padrão (se ainda não tiver)
ollama pull qwen2.5-coder:3b

# 3. Iniciar o Arquiteto Virtual
aponte architect
```

## 📂 Conheça sua Equipe (Catálogo)

### 🤖 Agentes Principais (Sua Squad)

- **`core/agents/architect.py`** (Architect Agent): **O Engenheiro.** Foca em Design e Interação Humana. Implementa a **Maestro Architecture** com **Reflex Engine** para respostas instantâneas e delegação inteligente.
- **`core/agents/sentinel.py`** (Sentinel Agent): **O Vigia.** Daemon distribuído. Utiliza **DynamoDB Locking (Race to Process)** para evitar duplicidade de alertas em times simultâneos.
- **`core/agents/auditor.py`** (Auditor Agent): **O Inspetor.** Executa varreduras de segurança estática (SAST) em arquivos. Não acessa a nuvem.
- **`core/agents/cloud_watcher.py`** (Observer Agent): **O Observador.** Monitora logs, custos (FinOps) e saúde da infraestrutura. Absorveu as capacidades de diagnóstico do Doctor.

### 🧠 Inteligência & Suporte

- **`core/services/knowledge/researcher.py`**: **O Pesquisador.** Serviço dedicado a ler documentação (Crawl4AI) e treinar o cérebro da IA. Desacoplado do Sentinel.
- **`core/services/doctor.py`**: **Sub-sistema de Diagnóstico.** Analisa logs, relatórios de segurança e **Audit Logs** para correlacionar erros com ações recentes (Causa e Efeito).
- **`core/tools/local_coder.py`**: **O Operário.** Gerador de código Terraform especializado com auto-correção (Self-Healing) e validação funcional (`terraform test`), executado localmente.
- **`core/tools/knowledge_cli.py`**: **O Professor.** Ferramenta para você ensinar coisas novas à IA (ingestão de docs) ou registrar decisões arquiteturais (ADRs).
- **`core/services/knowledge/trainer.py`**: **O Compilador.** Pega tudo que a IA aprendeu e "cimenta" em um novo modelo cerebral.
- **`core/services/llm_gateway.py`**: **O Gateway.** A ponte técnica que conecta os agentes ao Ollama ou AWS Bedrock.

### 🛠️ Ferramentas de Auditoria (O Cinto de Utilidades)

Estas são as ferramentas que os agentes usam por baixo dos panos. Você raramente precisará chamá-las diretamente.

- **`core/tools/git_auditor.py`**: Garante que o código da aplicação e da infraestrutura estejam falando a mesma língua.
- **`core/tools/path_auditor.py`**: Garante que a estrutura de pastas do projeto está organizada.
- **Externos:** `checkov`, `tfsec`, `tflint`, `infracost`, `hadolint`, `prowler`, `trivy`, `gitleaks`.

---

## 🤖 Guia de Uso: Como conversar com a máquina

A IA do A-PONTE foi desenhada para ser **segura por padrão**. Isso significa que alguns agentes têm "rituais" antes de obedecer.

### 🏗️ Architect Agent (`aponte architect`)

O **Architect Agent** é seu parceiro de pair-programming. Ele tem dois modos de humor:

#### 1. Modo Construtor (O Padrão Rígido)

Quando você inicia o chat, ele assume que você quer **trabalhar**. Para evitar criar recursos soltos ou sem padrão, ele exige um **Ritual de Iniciação**:

1.  **Objetivo:** Ele pergunta o que você vai fazer.
2.  **Contexto:** Ele deduz e preenche 4 variáveis vitais (`project_name`, `environment`, `app_name`, `infra_type`).
3.  **Contrato:** Você revisa e dá o "De Acordo" (Enter).

_Por que isso?_ Para garantir que todo recurso criado tenha as tags de custo e nomenclatura corretas (Multi-Tenant).

#### 2. Modo Livre (O Papo Cabeça)

Quer apenas tirar uma dúvida de AWS ou discutir arquitetura sem criar nada?

- No prompt de "Objetivo", digite: **`chat`**, **`duvida`** ou **`ola`**.
- O agente entenderá que é um momento "off-topic", carregará um contexto neutro (`playground`) e liberará o chat livre.

---

### 🛡️ Sentinel Agent (`aponte sentinel`)

Este é o agente que você deixa rodando em uma aba separada do terminal. Ele é proativo.

**O que ele faz enquanto você trabalha:**

1.  **Self-Audit:** A cada poucos ciclos, ele roda testes de segurança no seu código. Se você commitar algo inseguro, ele vai gritar (nos logs).
2.  **Threat Detection:** Monitora logs do CloudTrail em busca de anomalias (ex: Login de Root, Mudanças em Security Groups).
3.  **Drift Detection:** Verifica se a infraestrutura real divergiu do código Terraform.

---

### 🚑 AI Doctor (`aponte doctor`)

O "botão de pânico".

- **Quando usar:** O `terraform apply` quebrou? O container não sobe?
- **O que ele faz:** Lê o `system.log`, entende o erro, busca na memória se isso já aconteceu antes e te diz como resolver.

---

### 🕵️ Auditor Agent (`aponte audit`)

Seu revisor de código automatizado.

- **Modo Interativo:** Ele analisa arquivo por arquivo. Se achar erro, explica o problema e pergunta: _"Posso corrigir para você?"_. Se você disser sim, ele reescreve o código.
- **Modo Check (CI/CD):** Roda silencioso. Se achar erro, quebra o pipeline.

---

## 🛡️ Arquitetura de Segurança (Safety Nets)

A plataforma foi desenhada com múltiplas camadas de proteção para operar em ambientes críticos:

1.  **Isolamento de Contexto (ADR-027):**
    - O menu sempre inicia em estado neutro ("home") via injeção de memória.
    - Impossível realizar deploys acidentais ao abrir a ferramenta.

2.  **Leis da Robótica do A-PONTE (ADR-018):**
    - **Backup Automático:** Nenhuma ferramenta altera seu código sem antes salvar uma cópia versionada em `.aponte-versions/`.
    - **Sandbox de Validação:** Todo código gerado pela IA passa por validação de sintaxe (`terraform fmt`), linters de segurança e testes funcionais (`terraform test`) antes de ser sugerido.
    - **Memória Compartilhada:** O aprendizado de erros é persistido no DynamoDB, permitindo que a correção de um incidente beneficie todos os usuários.
    - **Isolamento de Dados:** A IA opera estritamente dentro do escopo do projeto atual (`project_name`), prevenindo vazamento de dados entre tenants.
    - **Break Glass Server-Side:** O acesso de emergência é revogado automaticamente pelo AWS EventBridge Scheduler, garantindo que credenciais temporárias não fiquem ativas indefinidamente.

## 🚀 Comandos Rápidos (Cheat Sheet)

| Ação          | Comando          | Descrição                                 |
| :------------ | :--------------- | :---------------------------------------- |
| **Conversar** | `aponte architect` | Inicia o Arquiteto Virtual.               |
| **Vigiar**    | `aponte sentinel`  | Inicia o Sentinela (Daemon).              |
| **Auditar**   | `aponte audit`     | Roda verificação de segurança e auto-fix. |
| **Curar**     | `aponte doctor`    | Diagnostica erros recentes.               |
| **Validar**   | `aponte ops pipeline` | Roda a esteira completa de qualidade.  |
