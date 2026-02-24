# 🛡️ Política de Segurança A-PONTE

A segurança é o pilar central da plataforma A-PONTE. Adotamos uma abordagem **"Secure by Design"** e **"Defense in Depth"**.

---

## 1. Princípios Fundamentais

### 🔐 Zero Credenciais Estáticas (ADR-001)

- **Não usamos Access Keys** (AKIA...) de longa duração para CI/CD.
- Toda autenticação é feita via **OIDC (OpenID Connect)** com GitHub Actions.
- Desenvolvedores usam credenciais temporárias (SSO/AWS CLI v2).

### 🚧 Permissions Boundary (ADR-002)

- Todas as Roles criadas pela plataforma possuem um **Permissions Boundary** anexado.
- Isso impede que uma Role de aplicação (mesmo com Admin) possa alterar suas próprias permissões ou criar usuários backdoor.

### 👁️ Visibilidade Total

- **Logs:** CloudTrail ativado em todas as contas.
- **Drift:** Detecção diária de alterações manuais (`aponte drift detect`).
- **Audit:** Varredura contínua com Prowler e Checkov.

---

## 2. Ferramentas de Segurança Integradas

A plataforma já vem com um arsenal de segurança configurado:

| Ferramenta      | Função                              | Comando                 |
| --------------- | ----------------------------------- | ----------------------- |
| **Checkov**     | Análise Estática (IaC)              | `aponte security checkov` |
| **Trivy**       | Vulnerabilidades em Containers/FS   | `aponte security trivy`   |
| **Prowler**     | Auditoria de Postura AWS (CIS/NIST) | `aponte security prowler` |
| **IA Security** | Auditoria Lógica e Correção         | `aponte audit`          |

---

## 3. Processo de Correção de Vulnerabilidades

Ao identificar uma vulnerabilidade (via Pipeline [W] ou Monitoramento):

1. **Analise:** Use o `aponte audit` para entender o risco e obter a correção sugerida.
2. **Corrija:** Aplique a correção no código Terraform (`.tf`).
3. **Valide:** Rode `aponte security checkov` localmente.
4. **Deploy:** Envie para o Git. O pipeline rodará novamente para confirmar.

---

## 4. Reportando Problemas

Se você encontrar uma falha de segurança na própria plataforma A-PONTE:

1. **Não abra uma Issue pública** no GitHub.
2. Envie um e-mail para `security@a-ponte.platform`.
3. Aguarde confirmação antes de divulgar.

---

## 5. Versões Suportadas

| Versão | Status   | Suporte de Segurança |
| ------ | -------- | -------------------- |
| 1.x    | ✅ Ativa | Sim                  |
| 0.x    | ❌ EOL   | Não                  |
