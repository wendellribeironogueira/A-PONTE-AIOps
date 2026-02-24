# 📚 Documentação A-PONTE

Bem-vindo à documentação técnica completa da plataforma **A-PONTE**, uma solução de **AIOps** para Engenharia de Plataforma. Esta seção contém guias detalhados, decisões arquiteturais e procedimentos operacionais.

---

## 🧠 Filosofia da Documentação (Brain as Code)

No A-PONTE, a documentação não é apenas para humanos lerem; ela é o **Código Fonte do Cérebro da IA**.

- **ADRs (`docs/adrs/`):** São as "Leis" que a IA deve seguir.
- **Knowledge Base (`docs/knowledge_base/`):** É a "Enciclopédia" (memória salva das interações via chat) que a IA consulta.
- **Manuais (`docs/*.md`):** São os "Procedimentos Operacionais Padrão" (SOPs).

## 📘 Guias de Uso

### Para Desenvolvedores e Analistas

- **[Mapa de Funcionalidades (FUNCTION_MAP.md)](./FUNCTION_MAP.md)** 👈 **Guia Tático**
  - Referência rápida de comandos: Quando usar [W] Pipeline, [L] Local ou [G] Git Audit.
- **[Workflows & Agentes (WORKFLOWS.md)](./WORKFLOWS.md)**
  - A Constituição da IA: Entenda como o Pipeline Unificado e a IA interagem.
- **[Guia de Integração (INTEGRATION_GUIDE.md)](./INTEGRATION_GUIDE.md)** 👈 **Comece aqui!**
  - Mapa de variáveis e segredos injetados pela plataforma
  - Como integrar seu código Terraform e GitHub Actions
  - Exemplos práticos de implementação

### Para Operadores

- **[Guia de Migração (MIGRATION.md)](./MIGRATION.md)**
  - Migração de ambientes v1.0 para v2.0
  - Passos de atualização e compatibilidade

- **[Plano de Migração CLI (CLI_MIGRATION_PLAN.md)](./CLI_MIGRATION_PLAN.md)**
  - Histórico da migração de scripts Bash para CLI Go
  - Status dos comandos migrados

### Para Administradores

- **[Guia de Offboarding (OFFBOARDING.md)](./OFFBOARDING.md)**
  - Procedimentos para remover projetos com segurança
  - Recuperação de backups e limpeza de recursos

- **[Disaster Recovery (DISASTER_RECOVERY.md)](./DISASTER_RECOVERY.md)**
  - Procedimentos de RTO/RPO
  - Recuperação de falhas críticas

- **[Troubleshooting (TROUBLESHOOTING.md)](./TROUBLESHOOTING.md)**
  - Guia de solução de problemas comuns
  - Escape Hatches e procedimentos de desbloqueio

---

## 🛡️ Segurança & Compliance

- **[Política de Segurança (SECURITY.md)](./SECURITY.md)**
  - Processo de report de vulnerabilidades
  - Versões suportadas e ciclo de vida

- **[Security Hardening Report](./security_hardening_report.md)**
  - Análise de segurança (Jan 2026)
  - Recomendações e melhorias implementadas

- **[Remediation Plan (REMEDIATION_PLAN.md)](./REMEDIATION_PLAN.md)**
  - Plano de correção de vulnerabilidades identificadas

---

## 🤖 Inteligência Artificial (Core)

- **[Chat Capabilities (CHAT_CAPABILITIES.md)](./CHAT_CAPABILITIES.md)**
  - Manual do Agente Arquiteto: Comandos, MCP e Contexto.

- **Agentes & Ferramentas (core/agents/README.md)**
  - Detalhes técnicos sobre a Squad de Agentes (Architect, Sentinel, Auditor, Observer).

## 🏗️ Arquitetura & Decisões Técnicas

- **[Architecture Decision Records (ADR.md)](./ADR.md)**
  - Histórico completo das decisões técnicas
  - Justificativas e consequências de cada escolha
  - Por que OIDC? Por que Terragrunt? Por que CLI Go?

---

## 🤝 Contribuindo

- **[Guia de Contribuição (contributing.md)](./contributing.md)**
  - Como contribuir para o projeto
  - Padrões de código e processo de PR

- **[Código de Conduta (CODE_OF_CONDUCT.md)](./CODE_OF_CONDUCT.md)**
  - Padrões de comportamento da comunidade

---

## 📝 Licença

- **[LICENSE](./LICENSE)**
  - Termos de licenciamento do projeto
