# 🚑 Plano de Recuperação de Desastres (DR)

Este documento descreve os procedimentos para recuperar a operação da plataforma **A-PONTE** em cenários de falha crítica.

---

## 1. Cenários de Falha

| Nível          | Cenário                             | Impacto                                | Procedimento                                                    |
| -------------- | ----------------------------------- | -------------------------------------- | --------------------------------------------------------------- |
| 🟡 **Médio**   | **Lock Preso** (DynamoDB)           | Terraform não consegue adquirir lock.  | [Desbloqueio Manual](#2-desbloqueio-de-estado-lock)             |
| 🟠 **Alto**    | **Corrupção de Estado** (.tfstate)  | Terraform falha ao ler o estado.       | [Rollback de Versão](#3-rollback-de-estado-s3)                  |
| 🔴 **Crítico** | **Falha no CI/CD** (GitHub Actions) | Pipeline fora do ar, deploy bloqueado. | [Break Glass (Emergência)](#4-acesso-de-emergência-break-glass) |
| ⚫ **Fatal**   | **Perda de Região AWS**             | Região inteira indisponível.           | [Redeploy em DR](#5-redeploy-em-região-de-dr)                   |

---

## 2. Desbloqueio de Estado (Lock)

Se um processo do Terraform for interrompido abruptamente, o Lock no DynamoDB pode ficar preso.

**Sintoma:**

> _Error: Error acquiring the state lock_

**Solução:**

1. Identifique o `LockID` na mensagem de erro.
2. Execute o comando de força bruta (use com cautela):
   ```bash
   terragrunt force-unlock <LOCK_ID>
   ```

---

## 3. Rollback de Estado (S3)

O A-PONTE ativa **Versionamento de S3** automaticamente para todos os buckets de estado. Se um `apply` corromper o arquivo de estado:

1. Acesse o Console AWS S3.
2. Navegue até o bucket do projeto: `aponte-state-<project>-<account>`.
3. Selecione o arquivo `terraform.tfstate`.
4. Na aba **Versions**, faça o download da versão anterior à corrupção.
5. Substitua a versão atual ou faça upload como nova versão atual.

---

## 4. Acesso de Emergência (Break Glass)

Se o GitHub Actions estiver fora do ar ou o OIDC falhar, utilize o modo **Break Glass** para acesso administrativo direto.

**Pré-requisitos:**

- Usuário IAM com permissão de assumir a role de suporte.
- Dispositivo MFA configurado.

**Procedimento:**

1. **Ativar Modo:**

   ```bash
   aponte break-glass enable
   ```

   _Isso configura suas credenciais locais para assumir a role `${Project}-SupportBreakGlassRole`._

2. **Executar Operação:**
   Realize o `terragrunt apply` ou `destroy` localmente.

3. **Desativar Modo (Obrigatório):**
   ```bash
   aponte break-glass disable
   ```
   _Nunca deixe o acesso de emergência ativo desnecessariamente._

---

## 5. Redeploy em Região de DR

Graças ao **Terragrunt** e à **Imutabilidade**, a infraestrutura pode ser recriada em outra região rapidamente.

1. Altere a variável `aws_region` no arquivo `.project.yml` ou `terragrunt.hcl`.
2. Execute o setup inicial:
   ```bash
   aponte setup bootstrap
   ```
3. Rediencione o tráfego DNS (Route53) para os novos endpoints.
