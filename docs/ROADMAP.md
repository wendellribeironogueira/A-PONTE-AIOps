# 🗺️ Roadmap de Evolução A-PONTE

> **Status:** Planejamento
> **Foco:** AIOps Nível 3 (Automação Cognitiva)

Este documento descreve o plano de evolução para o módulo de Inteligência Artificial (`ia_ops`) da plataforma, visando aumentar a robustez, segurança e autonomia dos agentes.

---

## 1. RAG "Lite" (Contexto Inteligente)

**Problema:** O envio de arquivos inteiros para o LLM consome muitos tokens e perde precisão em arquivos grandes.
**Solução:** Implementar busca semântica ou indexação simples.

- Criar índice local (JSON/SQLite) mapeando "Recursos" -> "Linhas do Arquivo".
- Ao analisar um erro, buscar apenas o bloco do recurso afetado e suas dependências.

## 2. Pipeline de "Self-Healing" com Validação (Sandbox)

**Problema:** A IA pode gerar código sintaticamente inválido, quebrando o Terraform.
**Solução:** Fluxo de tentativa e erro controlado.

1.  IA gera correção -> Salva em `temp_fix.tf`.
2.  Sistema roda `terraform validate`.
3.  **Passou:** Apresenta ao usuário.
4.  **Falhou:** Devolve o erro para a IA corrigir (Loop de Retry).

## 3. Agente DevOps Autônomo (Agentic Workflow)

**Problema:** A orquestração atual é linear e hardcoded (`pipeline.py`).
**Solução:** Transformar scripts em "Tools" que um Agente central pode invocar.

- O Agente recebe o objetivo ("Preparar para produção") e decide quais ferramentas rodar (`path_auditor`, `security_auditor`, `doc_bot`) dinamicamente baseada nos resultados intermediários.

## 4. Prompt Engineering Versionado

**Problema:** Prompts estão hardcoded no Python, dificultando ajustes finos.
**Solução:** Extrair prompts para arquivos de template (`ia_ops/prompts/*.txt`).

- Permite versionamento de prompts.
- Facilita testes A/B de diferentes estratégias de comando para a IA.

## 5. Feedback Loop Explícito (RLHF Lite)

**Problema:** O sistema não aprende com as correções aceitas ou rejeitadas.
**Solução:** Registrar o feedback do usuário.

- Adicionar status `Accepted`/`Rejected` no histórico do DynamoDB.
- Usar exemplos aceitos como "Few-Shot" no prompt para melhorar sugestões futuras.
