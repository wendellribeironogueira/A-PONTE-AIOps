# ==============================================================================
# RECURSOS GLOBAIS (SINGLETONS)
# ==============================================================================

# Obtém o certificado do endpoint OIDC do GitHub para extrair o thumbprint.
# Isso torna a configuração robusta a rotações de certificado pelo GitHub.
data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com"
}

# Provedor OIDC para federação com GitHub Actions (ADR-001)
# Criado uma única vez por conta AWS.
resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = ["sts.amazonaws.com"]

  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]

  tags = var.tags
}

# Tabela de Registro de Projetos (ADR-008)
# Recurso global, único por conta, para catalogar projetos e metadados.
resource "aws_dynamodb_table" "registry" {
  name         = "a-ponte-registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ProjectName"

  attribute {
    name = "ProjectName"
    type = "S"
  }

  # SEGURANÇA: Habilita recuperação de desastres (Point-in-Time Recovery)
  point_in_time_recovery {
    enabled = true
  }

  tags = merge(var.tags, {
    Name = "A-PONTE Registry"
  })
}
