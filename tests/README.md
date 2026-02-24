# 🧪 Testes Automatizados

Este diretório contém a suíte de testes unitários e de integração para os scripts Python da plataforma. Utilizamos `pytest` como runner e `unittest.mock` para isolar chamadas externas (AWS, Ollama, Git).

## 📂 Catálogo

### Testes de IA Ops

- **`test_ai_doctor.py`**: **Diagnóstico.** Testa o parser de logs e a integração com o `llm_client`. Mocka respostas do Ollama para garantir que a IA não alucine em testes.
- **`test_git_auditor.py`**: **Fluxo Git.** Valida a lógica de clonagem, detecção de tipo de repositório (App/Infra) e o mecanismo de backup antes do Auto-Fix.
- **`test_ia_ops.py`**: **Utilitários.** Testa funções auxiliares de sanitização de Markdown, validação de JSON e injeção de System Prompts.
- **`test_path_auditor.py`**: **Compliance.** Verifica se o auditor detecta corretamente estruturas de pastas inválidas ou arquivos obrigatórios ausentes.

### Testes de Orquestração

- **`test_pipeline.py`**: **Máquina de Estados.** Simula falhas em estágios do pipeline (ex: Security Scan falhando) para garantir que o processo pare imediatamente ("Fail Fast").
- **`test_guardrails.py`**: **Segurança.** (Inferred) Testa se as funções de bloqueio em `scripts/guardrails.py` impedem ações destrutivas em produção ou no contexto 'home'.

## 🚀 Como Rodar

```bash
# Executar todos os testes (Unitários + Integração)
make test

# Gerar relatório de cobertura (HTML + Terminal)
go test -cover ./...

# Verificar apenas integridade estrutural (Linting/Syntax)
python3 tests/integration/validate_integrity.py
```
