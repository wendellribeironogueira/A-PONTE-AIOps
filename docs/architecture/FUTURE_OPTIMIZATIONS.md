# 🚀 Otimizações Futuras e Estratégia de Modelos Híbridos

Este documento registra decisões arquiteturais e estratégias de otimização avaliadas para a evolução do A-PONTE, focando em eficiência de custos e performance local.

## 1. Estratégia de Modelos Híbridos (LangGraph)

Para otimizar a latência e o consumo de recursos em máquinas locais (Ollama), foi avaliada a viabilidade de usar modelos menores (0.5B - 1B) em conjunto com modelos padrão (3B+).

### Avaliação Técnica

1.  **FastMCP & Tool Calling (Modelos < 3B):**
    *   **Veredito:** Inviável para execução de ferramentas.
    *   **Motivo:** Modelos como `qwen2.5:0.5b` falham frequentemente na geração de JSON estruturado estrito necessário para o FastMCP, causando erros de sintaxe (`JSONDecodeError`) e alucinação de argumentos.
    *   **Recomendação:** O nó **Executor** deve manter modelos de no mínimo 3B parâmetros (ex: `llama3.2:3b`, `qwen2.5:3b`).

2.  **Roteamento e Classificação (Modelos < 3B):**
    *   **Veredito:** Altamente recomendado.
    *   **Uso:** Nós de decisão simples (Router, Critic) que exigem apenas saídas booleanas ou classificação de intenção.
    *   **Benefício:** Redução drástica de latência em loops de verificação.

### Implementação Proposta (Mix de Modelos)

O `LLMGateway` deve suportar um parâmetro `size` ou `profile` para selecionar o modelo adequado por nó do grafo.

```python
# Exemplo de Roteamento no Grafo
def router_node(state):
    # Usa modelo nano (0.5B) para decisão rápida
    decision = gateway.chat(..., config=LLMConfig(size="nano"))
    return decision

def executor_node(state):
    # Usa modelo standard (3B+) para gerar JSON/Terraform
    return gateway.chat(..., config=LLMConfig(size="standard"))
```

## 2. Otimização do Grafo (LangGraph)

### Ciclo de Síntese (Read-Eval-Print)
O fluxo original `Executor -> Tools -> Critic` resultava em respostas "cruas" (raw output).

**Correção Aplicada (v2):**
*   Fluxo: `Executor -> Tools -> Executor -> Critic`
*   Isso garante que, após uma ferramenta retornar dados (ex: leitura de doc), o LLM (Executor) tenha a chance de ler esses dados e formular uma resposta em linguagem natural antes de encerrar o passo.

## 3. Hardware Mínimo Recomendado (Local)

| Perfil | RAM | VRAM | Modelos Sugeridos |
| :--- | :--- | :--- | :--- |
| **Ultra Low** | 8GB | N/A | Qwen 2.5 0.5B (Router) + Llama 3.2 1B (Chat) |
| **Standard** | 16GB | 4GB | Llama 3.2 3B (All) |
| **High** | 32GB | 8GB+ | DeepSeek R1 (Reasoning) + Llama 3.3 70B (Coding) |

## 4. Roadmap de Implementação

1.  **Otimização de Modelos Híbridos:**
    *   [x] **Gateway (`llm_gateway.py`):** Implementar suporte ao parâmetro `size="nano"` para selecionar modelos leves.
    *   [x] **Grafo (`graph_architect.py`):** Criar/Refatorar nós para usar modelos "nano" em tarefas específicas (Ex: `_critic_node`).

2.  **Refatoração Estrutural (Manutenibilidade e Robustez):**
    *   [x] **Gateway (`llm_gateway.py`):** Desacoplar lógica de fallback para evitar "amnésia" do agente.
    *   [x] **Grafo (`graph_architect.py`):** Implementar tratamento de falhas do gateway (ex: retry ou mudança de provedor no estado).
    *   [x] **Agente (`architect.py`):** Transformar em um "Cliente Leve" do grafo. (Concluído: Toda a lógica de negócio, incluindo prompts, orquestração e interação de contexto, foi removida. O agente agora é um cliente puro do `GraphArchitect`).

3.  **Persistência e Resiliência do Grafo:**
    *   [x] **Checkpointing Durável:** Implementado com `SqliteSaver`. O estado da conversa agora é persistido em `data/checkpoints.sqlite`, permitindo a retomada de sessões.

## 5. Guia de Refatoração Estrutural (Agent & Gateway)


Esta seção detalha as melhorias arquiteturais recomendadas para aumentar a manutenibilidade, robustez e eficiência do sistema de agentes.

### 5.1. Refatoração do `ArchitectAgent` (O Maestro)

*   **Objetivo:** Simplificar para Orquestrar.
*   **Diagnóstico:** O agente (`core/agents/architect.py`) concentra muitas responsabilidades (gerenciamento de chat, construção de prompts, lógica de contexto interativo), tornando-se um "Objeto Divino" (God Object) e dificultando a manutenção.
*   **Solução Proposta:** Transformar o `ArchitectAgent` em um **"Cliente Leve"** do Grafo LangGraph.
    1.  **Mover Lógica para o Grafo:** A lógica de negócio deve residir nos nós do grafo.
        *   A função `_define_context_interactive` deve ser convertida em uma **ferramenta MCP** (ex: `prompt_user_for_context`) que o `ExecutorNode` pode invocar quando o estado do projeto for indefinido.
        *   A construção de prompts complexos deve ser distribuída: cada nó (`planner`, `executor`) deve ter seu próprio prompt, simples e focado.
    2.  **Simplificar o Loop Principal:** O método `run()` do agente deve apenas gerenciar o estado da sessão e invocar o grafo, delegando todo o fluxo de controle para o LangGraph.
*   **Benefício:** O fluxo de controle torna-se explícito e visual no grafo, facilitando o debug e a extensão com novos nós ou ferramentas.

### 5.2. Refatoração do `LLMGateway` (O Motor)

*   **Objetivo:** Aumentar a Robustez e a Eficiência.
*   **Diagnóstico 1 (Falha Crítica):** O mecanismo de fallback para Ollama causa **"amnésia"** no agente. Ao falhar a chamada para o Gemini, o gateway reseta o histórico da conversa, fazendo o agente perder todo o contexto anterior.
*   **Solução 1 (Desacoplamento):** O `LLMGateway` **não deve gerenciar o estado da conversa ou o fallback**. Sua responsabilidade é apenas executar a chamada à API.
    *   Em caso de falha (ex: rate limit, erro de API), o gateway deve **sinalizar o erro** (retornando `None` ou levantando uma exceção).
    *   O **nó do LangGraph** que invocou o gateway é quem deve capturar a falha e decidir o que fazer: tentar novamente, ou mudar o provedor de IA no `AgentState` e re-executar o passo.
*   **Diagnóstico 2 (Otimização):** A implementação da estratégia de **Modelos Híbridos** está pendente.
*   **Solução 2 (Implementação):** Finalizar a lógica no `llm_gateway.py` para que, ao receber o parâmetro `size="nano"`, o gateway selecione um modelo leve (ex: `qwen2.5:0.5b`) para tarefas simples como roteamento e classificação, reduzindo latência.

### 5.3. Melhorias no `GraphArchitect` (O Cérebro)

*   **Objetivo:** Manter a simplicidade e adicionar robustez.
*   **Sugestão 1 (Nó Crítico):** Manter o `_critic_node` simples. Sua função principal deve ser avançar o plano (`current_step`). Evitar adicionar lógica de IA complexa neste nó para não introduzir latência e alucinações.
*   **Sugestão 2 (Nó Planejador):** Adicionar tratamento de erro mais explícito no `_planner_node` para logar quando o LLM falhar em gerar um JSON válido, facilitando o debug de prompts.