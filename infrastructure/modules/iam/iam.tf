# Política para permitir que os projetos acessem APENAS seus próprios registros
resource "aws_iam_policy" "registry_access" {
  name        = lower("aponte-registry-access-${var.project_name}")
  description = "Permite acesso restrito ao registro do projeto ${var.project_name}"
  path        = "/"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowTableAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query"
        ]
        Resource = var.registry_table_arn
        Condition = {
          # ISOLAMENTO MULTI-TENANT:
          # Garante que o projeto só pode ler/escrever itens onde
          # a Partition Key (ProjectName) é igual ao nome do projeto atual.
          "ForAllValues:StringEquals" = {
            "dynamodb:LeadingKeys" = [
              lower(var.project_name)
            ]
          }
        }
      },
      {
        Sid    = "AllowDescribeTable"
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeTable"
        ]
        Resource = var.registry_table_arn
      }
    ]
  })

  tags = {
    Project = var.project_name
  }
}
