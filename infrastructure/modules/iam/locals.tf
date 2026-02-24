# terraform/modules/identity/locals.tf

locals {
  # =================================================================================
  # Variáveis Derivadas e ARNs
  # =================================================================================
  account_id   = data.aws_caller_identity.current.account_id
  project_name = var.project_name

  # ARNs para Backend e Logging
  arn_s3_tfstate     = "arn:aws:s3:::a-ponte-central-tfstate-${local.account_id}"
  arn_dynamodb_lock  = "arn:aws:dynamodb:${var.aws_region}:${local.account_id}:table/a-ponte-lock-${local.project_name}"
  arn_s3_config_logs = "arn:aws:s3:::aws-config-bucket-${local.account_id}"
  arn_s3_audit_logs  = "arn:aws:s3:::a-ponte-audit-logs"

  # ARNs para Recursos do Projeto
  arn_s3_project_all     = "arn:aws:s3:::${local.project_name}-*"
  arn_iam_role_project   = "arn:aws:iam::${local.account_id}:role/${local.project_name}-*"
  arn_iam_policy_project = "arn:aws:iam::${local.account_id}:policy/${local.project_name}-*"

  # =================================================================================
  # Data Sources
  # =================================================================================
}

data "aws_caller_identity" "current" {}

locals {
  # =================================================================================
  # Ações Explícitas por Serviço (Princípio do Menor Privilégio)
  # =================================================================================

  # Ações S3 para gerenciamento de buckets de state, logs e aplicações.
  s3_read_actions = [
    "s3:GetObject",
    "s3:ListBucket",
    "s3:GetBucketVersioning",
    "s3:GetBucketLocation",
    "s3:GetBucketPolicy",
    "s3:GetBucketAcl",
    "s3:GetBucketEncryption",
    "s3:GetPublicAccessBlock",
    "s3:ListAllMyBuckets",
  ]
  s3_write_actions = [
    "s3:PutObject",
    "s3:DeleteObject",
    "s3:DeleteObjectVersion",
    "s3:PutBucketVersioning",
    "s3:PutBucketEncryption",
    "s3:PutBucketPolicy",
    "s3:PutBucketAcl",
    "s3:PutPublicAccessBlock",
  ]
  s3_admin_actions = concat(
    local.s3_read_actions,
    local.s3_write_actions,
    [
      "s3:CreateBucket",
      "s3:DeleteBucket",
    ]
  )

  # Ações DynamoDB para tabelas de lock e registro.
  dynamodb_admin_actions = [
    "dynamodb:CreateTable",
    "dynamodb:DeleteTable",
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:UpdateItem",
    "dynamodb:DeleteItem",
    "dynamodb:DescribeTable",
    "dynamodb:ListTables",
  ]

  # Ações IAM para gerenciamento de roles e policies pelo CI/CD.
  iam_write_actions = [
    "iam:CreateRole",
    "iam:DeleteRole",
    "iam:PutRolePermissionsBoundary",
    "iam:DeleteRolePermissionsBoundary",
    "iam:AttachRolePolicy",
    "iam:DetachRolePolicy",
    "iam:TagRole",
    "iam:UntagRole",
    "iam:CreatePolicy",
    "iam:DeletePolicy",
    "iam:TagPolicy",
    "iam:UntagPolicy",
    "iam:PassRole",
    "iam:CreateInstanceProfile",
    "iam:DeleteInstanceProfile",
    "iam:AddRoleToInstanceProfile",
    "iam:RemoveRoleFromInstanceProfile",
    "iam:DeleteRolePolicy",
    "iam:PutRolePolicy",
  ]
  iam_read_actions = [
    "iam:GetRole",
    "iam:GetPolicy",
    "iam:ListRoles",
    "iam:ListPolicies",
    "iam:ListRolePolicies",
    "iam:GetInstanceProfile",
    "iam:GetOpenIDConnectProvider",
    "iam:ListOpenIDConnectProviders",
  ]

  # Ações EC2
  ec2_read_actions = [
    "ec2:DescribeInstances", "ec2:DescribeImages", "ec2:DescribeVpcs", "ec2:DescribeSubnets",
    "ec2:DescribeSecurityGroups", "ec2:DescribeRouteTables", "ec2:DescribeNetworkAcls",
    "ec2:DescribeVolumes", "ec2:DescribeAddresses",
  ]
  ec2_create_actions = [
    "ec2:RunInstances", "ec2:CreateVolume", "ec2:CreateSecurityGroup",
    "ec2:AuthorizeSecurityGroupIngress", "ec2:AuthorizeSecurityGroupEgress",
    "ec2:CreateSubnet", "ec2:CreateVpc", "ec2:AllocateAddress",
  ]
  ec2_modify_actions = [
    "ec2:ModifyInstanceAttribute", "ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress",
    "ec2:AssociateRouteTable", "ec2:DisassociateRouteTable",
  ]
  ec2_destructive_actions = [
    "ec2:TerminateInstances", "ec2:StopInstances", "ec2:RebootInstances", "ec2:DeleteVolume",
    "ec2:DeleteSecurityGroup", "ec2:DeleteSubnet", "ec2:DeleteVpc", "ec2:ReleaseAddress",
    "ec2:AttachVolume", "ec2:DetachVolume",
  ]
  ec2_tagging_actions = ["ec2:CreateTags", "ec2:DeleteTags"]

  # Ações ECR
  ecr_write_actions = [
    "ecr:CreateRepository", "ecr:DeleteRepository", "ecr:PutImage", "ecr:InitiateLayerUpload",
    "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:BatchDeleteImage", "ecr:SetRepositoryPolicy",
  ]

  # Ações SSM
  ssm_write_actions = [
    "ssm:PutParameter", "ssm:DeleteParameter", "ssm:AddTagsToResource", "ssm:RemoveTagsFromResource",
  ]
  ssm_read_actions = [
    "ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath", "ssm:DescribeParameters",
    "ssm:DescribeInstanceInformation", "ssm:GetCommandInvocation", "ssm:ListCommandInvocations",
    "ssm:ListCommands", "ssm:GetDocument", "ssm:DescribeDocument", "ssm:CancelCommand"
  ]

  # Ações de Observabilidade
  observability_read_actions = [
    "logs:DescribeLogGroups", "logs:DescribeLogStreams", "logs:GetLogEvents",
    "cloudwatch:DescribeAlarms", "cloudwatch:GetMetricData", "cloudtrail:DescribeTrails",
    "config:DescribeConfigRules",
  ]
  observability_write_actions = [
    "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "cloudwatch:PutMetricData",
    "cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudtrail:CreateTrail",
    "cloudtrail:DeleteTrail", "config:PutConfigRule", "config:DeleteConfigRule",
    "config:PutConfigurationRecorder", "config:DeleteConfigurationRecorder", "config:PutDeliveryChannel",
    "config:DeleteDeliveryChannel",
  ]
}
