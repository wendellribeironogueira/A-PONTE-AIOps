# 🧠 Núcleo de Inteligência Artificial (Core Agents)

Este diretório contém a implementação dos **Agentes Autônomos** que impulsionam a plataforma A-PONTE. Aqui reside a lógica de orquestração, engenharia de prompt e integração com ferramentas (Tool Use).

---

## 🧩 Arquitetura dos Agentes

Os agentes do A-PONTE seguem o padrão **ReAct (Reasoning + Acting)**, combinando a capacidade de raciocínio de LLMs com a execução segura de ferramentas via MCP (Model Context Protocol).

### Componentes Chave

1.  **Cérebro (LLM Gateway):**
    *   Abstração para comunicação com provedores de inferência (Ollama, AWS Bedrock).
    *   Gerencia o contexto e a memória de curto prazo.
2.  **Mãos (MCP Clients):**
    *   Executores especializados que rodam em ambientes isolados.
    *   Ex: `mcp-terraform` (Docker) para IaC, `mcp-aws` (Boto3) para leitura de nuvem.
3.  **Memória (Knowledge Base):**
    *   Sistema RAG (Retrieval-Augmented Generation) que injeta documentação e histórico de erros no contexto da IA.

---

## 🤖 Catálogo de Agentes

### 1. Architect Agent (`architect.py`)
*   **Persona:** Arquiteto de Soluções Sênior / DevOps.
*   **Responsabilidade:** Interface primária com o usuário. Gerencia o ciclo de vida de projetos e geração de código.
*   **Fluxo de Trabalho:**
    1.  **Discovery:** Entrevista o usuário para definir o contexto (Projeto, Ambiente, App).
    2.  **Design:** Propõe a arquitetura utilizando módulos Terraform padronizados.
    3.  **Execution:** Gera o código, valida no Sandbox e aplica via Terragrunt.
*   **Diferencial:** Possui "Memória de Sessão", aprendendo com as correções do usuário e persistindo o conhecimento.

### 2. Sentinel Agent (`sentinel.py`)
*   **Persona:** Analista de Segurança (SecOps) / Guardião.
*   **Responsabilidade:** Monitoramento passivo e ativo. Roda em background.
*   **Ciclos de Vigilância:**
    *   **Self-Audit:** Verifica vulnerabilidades no código local.
    *   **Drift Hunter:** Compara o estado real da AWS com o código Terraform.

### 3. Auditor Agent (`auditor.py`)
*   **Persona:** Revisor de Código (Code Reviewer).
*   **Responsabilidade:** Garantia de qualidade e segurança estática (SAST).
*   **Integrações:** Conecta-se ao **DefectDojo** para centralizar a gestão de vulnerabilidades encontradas.

### 4. Observer Agent (`cloud_watcher.py`)
*   **Persona:** Engenheiro de Confiabilidade (SRE).
*   **Responsabilidade:** Diagnóstico e Observabilidade.
*   **Capacidades:**
    *   Consulta logs do CloudWatch e CloudTrail usando linguagem natural.
    *   Correlaciona eventos de erro com mudanças na infraestrutura.
    *   **FinOps:** Monitora custos e sugere otimizações baseadas em dados reais.

---

##  Ciclo de Aprendizado Contínuo

A inteligência da plataforma não é estática. Ela evolui através de um pipeline de conhecimento:

1.  **Descoberta (Discovery):**
    *   **Quem:** Researcher Agent (`aponte ai ingest`).
    *   **O que faz:** Pesquisa proativamente na web por novas práticas (AWS, Terraform, FinOps) e adiciona URLs promissoras ao arquivo `docs/sources.txt`.
2.  **Ingestão (Ingestion):**
    *   **Quem:** Ingestor (`core/services/knowledge/ingestor.py`).
    *   **O que faz:** Lê a fila de `docs/sources.txt`, baixa o conteúdo das páginas, limpa o HTML e salva snippets em `docs/knowledge_base/`.
3.  **Treinamento (Training):**
    *   **Quem:** Trainer (`aponte ai train`).
    *   **O que faz:** Compila todos os arquivos Markdown (`docs/`) em um novo `Modelfile` e atualiza o modelo `aponte-ai` no Ollama.

---

## 🛠️ Desenvolvimento de Novos Agentes

Para criar um novo agente, herde da classe `BaseAgent` e implemente o método `run()`:

```python
from core.agents.base import BaseAgent

class MyNewAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="Specialist", description="Agente Especialista")

    def run(self):
        # Lógica do loop de execução
        pass
```
