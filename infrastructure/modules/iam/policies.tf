locals {
  # SEGURANÇA: Lista explícita de ações permitidas (Least Privilege)
  required_s3_actions = [
    "s3:CreateBucket",
    "s3:DeleteBucket",
    "s3:ListBucket",
    "s3:GetBucket*",
    "s3:PutBucketPolicy",
    "s3:PutBucketTagging",
    "s3:PutBucketVersioning",
    "s3:PutBucketPublicAccessBlock",
    "s3:PutBucketAcl",
    "s3:PutBucketCORS",
    "s3:PutLifecycleConfiguration",
    "s3:PutEncryptionConfiguration",
    "s3:PutBucketLogging",
    "s3:PutBucketWebsite",
    "s3:GetObject",
    "s3:PutObject",
    "s3:DeleteObject"
  ]

  required_dynamodb_actions = [
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:DeleteItem",
    "dynamodb:DescribeTable"
  ]
}

data "aws_iam_policy_document" "oidc_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for repo in var.github_repos : "repo:${repo}:*"]
    }
  }
}

data "aws_iam_policy_document" "devops_policy" {
  statement {
    sid       = "IAMCreateActions"
    effect    = "Allow"
    actions   = ["iam:CreateRole", "iam:CreatePolicy", "iam:TagRole"]
    resources = ["arn:aws:iam::${var.account_id}:role/${lower(var.project_name)}-*", "arn:aws:iam::${var.account_id}:policy/${lower(var.project_name)}-*"]

    # ISOLAMENTO: Impede a criação de Roles/Policies órfãs (sem tag de projeto)
    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Project"
      values   = [var.project_name]
    }
  }

  statement {
    sid    = "IAMManageActions"
    effect = "Allow"
    actions = [
      "iam:DeleteRole", "iam:PassRole", "iam:PutRolePermissionsBoundary",
      "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:DeletePolicy",
      "iam:CreatePolicyVersion", "iam:DeletePolicyVersion", "iam:UntagRole"
    ]
    resources = ["arn:aws:iam::${var.account_id}:role/${lower(var.project_name)}-*", "arn:aws:iam::${var.account_id}:policy/${lower(var.project_name)}-*"]
  }

  statement {
    sid       = "IAMGlobalReadActions"
    effect    = "Allow"
    actions   = ["iam:List*"]
    resources = ["*"]
  }

  statement {
    sid       = "IAMScopedGetActions"
    effect    = "Allow"
    actions   = ["iam:Get*"]
    resources = ["arn:aws:iam::${var.account_id}:role/${lower(var.project_name)}-*", "arn:aws:iam::${var.account_id}:policy/${lower(var.project_name)}-*", var.oidc_provider_arn]
  }

  statement {
    sid     = "S3ExplicitActions"
    effect  = "Allow"
    actions = local.required_s3_actions
    resources = [
      "arn:aws:s3:::${lower(var.project_name)}-*",
      "arn:aws:s3:::${lower(var.project_name)}-*/*"
    ]
  }

  # SEGURANÇA: Permissões restritas para o Backend Centralizado
  # Remove permissão de 's3:DeleteBucket' no bucket de estado compartilhado
  statement {
    sid    = "S3BackendAccess"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:GetBucketVersioning",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject" # Necessário para remover state lock/arquivos, mas não o bucket
    ]
    resources = [
      "arn:aws:s3:::a-ponte-central-tfstate-${var.account_id}",
      "arn:aws:s3:::a-ponte-central-tfstate-${var.account_id}/${var.project_name}/*"
    ]
  }

  statement {
    sid       = "DynamoDBLockAccess"
    effect    = "Allow"
    actions   = local.required_dynamodb_actions
    resources = ["arn:aws:dynamodb:${var.aws_region}:${var.account_id}:table/a-ponte-lock-table"]
  }
}

data "aws_iam_policy_document" "boundary" {
  # 1. Permite tudo explicitamente (dentro do boundary)
  statement {
    sid       = "AllowAllOperations"
    effect    = "Allow"
    actions   = ["*"]
    resources = ["*"]
  }

  # 2. Bloqueia alteração do próprio boundary
  statement {
    sid    = "DenyBoundaryEscape"
    effect = "Deny"
    actions = [
      "iam:DeleteRolePermissionsBoundary",
      "iam:PutRolePermissionsBoundary"
    ]
    resources = ["*"]
    condition {
      test     = "StringNotLike"
      variable = "iam:PermissionsBoundary"
      values   = ["arn:aws:iam::${var.account_id}:policy/${lower(var.project_name)}-infra-boundary"]
    }
  }

  # 3. SEGURANÇA (Hardening): Impede criação de roles sem boundary
  statement {
    sid       = "DenyRoleCreationWithoutBoundary"
    effect    = "Deny"
    actions   = ["iam:CreateRole"]
    resources = ["*"]
    condition {
      test     = "StringNotEquals"
      variable = "iam:PermissionsBoundary"
      values   = ["arn:aws:iam::${var.account_id}:policy/${lower(var.project_name)}-infra-boundary"]
    }
  }

  # 4. Bloqueia criação de usuários IAM (apenas Roles permitidas)
  statement {
    sid       = "DenyIAMUserManagement"
    effect    = "Deny"
    actions   = ["iam:CreateUser", "iam:DeleteUser", "iam:UpdateUser"]
    resources = ["*"]
  }
}
