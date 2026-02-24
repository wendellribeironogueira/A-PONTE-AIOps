🚨 REGRAS DE SEGURANÇA:
1. Least Privilege: Nunca permita 0.0.0.0/0 em portas 22 (SSH) ou 3389 (RDP).
2. Encryption: Force criptografia em S3/RDS/EBS (Use SSE-S3/AWS Managed).
   - PROIBIDO: Não use KMS CMK (`aws_kms_key`). Se encontrar `kms_master_key_id`, REMOVA.
   - Para S3, use `sse_algorithm = "AES256"`.
3. Sintaxe: O código gerado deve ser Terraform HCL válido.
   - Use APENAS aspas duplas ("). Aspas simples (') são PROIBIDAS em HCL.
   - Não invente atributos (ex: allowVisibility). Use apenas blocos padrão.
4. Cloud Provider: Foco EXCLUSIVO em AWS. Ignore Azure/GCP.
5. Variáveis de Contexto (Multi-Tenant):
   - Ao corrigir nomes ou tags, use SEMPRE as variáveis padrão:
     - var.project_name (para prefixos de recursos)
     - var.environment (para tags)
     - var.aws_region (NUNCA sugira hardcoding de região como 'us-east-1'. O uso de variável é a prática correta).
     - var.app_name (para tags de aplicação)
   - Não hardcode nomes de ambientes (ex: "prod"). Use "${var.environment}".
   - PROPRIEDADE: O recurso pertence a `var.project_name`. Garanta que VPCs e Security Groups tenham esse prefixo no `name` ou `tags`.
   - 🛑 EXCEÇÃO ABSOLUTA (BACKEND/TERRAGRUNT):
     - Em arquivos `backend.tf` ou blocos `terraform { backend ... }`, o uso de variáveis é TÉCNICAMENTE IMPOSSÍVEL.
     - É ESTRITAMENTE PROIBIDO sugerir a troca de strings hardcoded (ex: "a-ponte-...") por `${var.project_name}` dentro do bloco `backend`.
     - Se o arquivo for `backend.tf` e contiver nomes hardcoded, considere isso CORRETO e SEGURO. Não altere.
6. ADR-003 (Bootstrap): É PROIBIDO criar recursos de Backend (S3 State Bucket, DynamoDB Lock Table) manualmente em .tf. O Terragrunt gerencia isso. Se encontrar, remova ou marque como violação.