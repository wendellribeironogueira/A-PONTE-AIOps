data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# =================================================================================
# MÓDULO DE OBSERVABILIDADE
# =================================================================================

# --- AWS Config ---
resource "aws_config_configuration_recorder" "main" {
  count    = var.create_global_resources ? 1 : 0
  name     = lower("${var.project_name}-config-recorder")
  role_arn = aws_iam_role.config[0].arn
  recording_group {
    all_supported                 = true
    include_global_resource_types = true
  }
}

resource "aws_config_delivery_channel" "main" {
  count          = var.create_global_resources ? 1 : 0
  name           = lower("${var.project_name}-config-delivery")
  s3_bucket_name = var.config_bucket_name
  sns_topic_arn  = aws_sns_topic.config_compliance[0].arn
  depends_on     = [aws_config_configuration_recorder.main[0], aws_s3_bucket_policy.config[0]]
}

resource "aws_config_configuration_recorder_status" "main" {
  count      = var.create_global_resources ? 1 : 0
  name       = aws_config_configuration_recorder.main[0].name
  is_enabled = true
  depends_on = [aws_config_delivery_channel.main[0]]
}

data "aws_iam_policy_document" "config_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["config.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "config" {
  count                = var.create_global_resources ? 1 : 0
  name                 = lower("${var.project_name}-config-role")
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
  assume_role_policy   = data.aws_iam_policy_document.config_assume_role.json
}

resource "aws_iam_role_policy_attachment" "config" {
  count      = var.create_global_resources ? 1 : 0
  role       = aws_iam_role.config[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWS_ConfigRole"
}

# --- CloudTrail ---
resource "aws_cloudtrail" "main" {
  count                         = var.create_global_resources ? 1 : 0
  name                          = lower("${var.project_name}-main-trail")
  s3_bucket_name                = var.audit_logs_bucket_name
  include_global_service_events = true
  is_multi_region_trail         = true # CIS 2.1 Compliance
  enable_log_file_validation    = true
  cloud_watch_logs_group_arn    = "${aws_cloudwatch_log_group.cloudtrail[0].arn}:*"
  cloud_watch_logs_role_arn     = aws_iam_role.cloudtrail_cloudwatch[0].arn
  tags                          = var.tags
  depends_on                    = [aws_s3_bucket_policy.audit_logs[0]]
}

resource "aws_cloudwatch_log_group" "cloudtrail" {
  count             = var.create_global_resources ? 1 : 0
  name              = "/aws/cloudtrail/${lower(var.project_name)}"
  retention_in_days = var.log_retention_days # LGPD Compliance
  tags              = var.tags
}

data "aws_iam_policy_document" "cloudtrail_cw_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cloudtrail_cloudwatch" {
  count                = var.create_global_resources ? 1 : 0
  name                 = lower("${var.project_name}-cloudtrail-cw-role")
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
  assume_role_policy   = data.aws_iam_policy_document.cloudtrail_cw_assume_role.json
}

data "aws_iam_policy_document" "cloudtrail_cw_policy" {
  count = var.create_global_resources ? 1 : 0
  statement {
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.cloudtrail[0].arn}:*"]
  }
}

resource "aws_iam_role_policy" "cloudtrail_cloudwatch" {
  count  = var.create_global_resources ? 1 : 0
  name   = lower("${var.project_name}-cloudtrail-cw-policy")
  role   = aws_iam_role.cloudtrail_cloudwatch[0].id
  policy = data.aws_iam_policy_document.cloudtrail_cw_policy[0].json
}

# --- Tópicos SNS ---
resource "aws_sns_topic" "config_compliance" {
  count = var.create_global_resources ? 1 : 0
  name  = lower("${var.project_name}-config-compliance")
  tags  = var.tags
}

# --- Alarmes ---
resource "aws_cloudwatch_log_metric_filter" "root_usage" {
  count          = var.create_global_resources ? 1 : 0
  name           = lower("${var.project_name}-root-usage")
  log_group_name = aws_cloudwatch_log_group.cloudtrail[0].name
  pattern        = "{ $.userIdentity.type = \"Root\" && $.userIdentity.invokedBy NOT EXISTS && $.eventType != \"AwsServiceEvent\" }"
  metric_transformation {
    name      = "RootAccountUsage"
    namespace = "CloudTrailMetrics"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "root_usage" {
  count               = var.create_global_resources ? 1 : 0
  alarm_name          = lower("${var.project_name}-root-usage")
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "RootAccountUsage"
  namespace           = "CloudTrailMetrics"
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "ALERTA CRITICO: A conta ROOT foi utilizada!"
  alarm_actions       = [var.sns_topic_arn]
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

resource "aws_cloudwatch_log_metric_filter" "cloudtrail_tampering" {
  count          = var.create_global_resources ? 1 : 0
  name           = lower("${var.project_name}-cloudtrail-tampering")
  log_group_name = aws_cloudwatch_log_group.cloudtrail[0].name
  pattern        = "{ ($.eventName = StopLogging) || ($.eventName = DeleteTrail) || ($.eventName = UpdateTrail) || ($.eventName = DeleteGroup) || ($.eventName = DeleteLogStream) }"
  metric_transformation {
    name      = "CloudTrailTampering"
    namespace = "CloudTrailMetrics"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "cloudtrail_tampering" {
  count               = var.create_global_resources ? 1 : 0
  alarm_name          = lower("${var.project_name}-cloudtrail-tampering")
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "CloudTrailTampering"
  namespace           = "CloudTrailMetrics"
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "ALERTA CRITICO: Tentativa de alteracao no CloudTrail!"
  alarm_actions       = [var.sns_topic_arn]
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

# --- Regras do AWS Config (Conformidade) ---
resource "aws_config_config_rule" "root_mfa" {
  count = var.create_global_resources ? 1 : 0
  name  = "root-account-mfa-enabled"

  source {
    owner             = "AWS"
    source_identifier = "ROOT_ACCOUNT_MFA_ENABLED"
  }

  depends_on = [aws_config_configuration_recorder.main[0]]
  tags       = var.tags
}

resource "aws_config_config_rule" "encrypted_volumes" {
  count = var.create_global_resources ? 1 : 0
  name  = "encrypted-volumes"

  source {
    owner             = "AWS"
    source_identifier = "ENCRYPTED_VOLUMES"
  }

  depends_on = [aws_config_configuration_recorder.main[0]]
  tags       = var.tags
}

resource "aws_config_config_rule" "s3_encryption" {
  count = var.create_global_resources ? 1 : 0
  name  = "s3-bucket-server-side-encryption-enabled"

  source {
    owner             = "AWS"
    source_identifier = "S3_BUCKET_SERVER_SIDE_ENCRYPTION_ENABLED"
  }

  depends_on = [aws_config_configuration_recorder.main[0]]
  tags       = var.tags
}

# --- Dashboard do CloudWatch (P3 - Item 15) ---
resource "aws_cloudwatch_dashboard" "main" {
  count          = var.create_global_resources ? 1 : 0
  dashboard_name = lower("${var.project_name}-main-dashboard")
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric",
        x      = 0,
        y      = 0,
        width  = 8,
        height = 6,
        properties = {
          metrics = [
            ["CloudTrailMetrics", "RootAccountUsage", { "label" = "Uso da Conta Root" }]
          ],
          view    = "timeSeries",
          stacked = false,
          region  = data.aws_region.current.id,
          title   = "🚨 Segurança: Conta Root",
          period  = 300
        }
      },
      {
        type   = "metric",
        x      = 8,
        y      = 0,
        width  = 8,
        height = 6,
        properties = {
          metrics = [
            ["CloudTrailMetrics", "CloudTrailTampering", { "label" = "Tampering" }],
            ["Security/Identity", "BoundaryViolationCount", { "label" = "Boundary Violations" }]
          ],
          view    = "timeSeries",
          stacked = false,
          region  = data.aws_region.current.id,
          title   = "🛡️ Integridade & IAM",
          period  = 300
        }
      },
      {
        type   = "metric",
        x      = 16,
        y      = 0,
        width  = 8,
        height = 6,
        properties = {
          metrics = [
            ["AWS/Billing", "EstimatedCharges", "Currency", "USD", { "label" = "Custo Estimado (USD)", "region" = "us-east-1" }]
          ],
          view   = "singleValue",
          region = "us-east-1",
          title  = "💰 FinOps: Custo Mensal",
          period = 21600
        }
      },
      {
        type   = "metric",
        x      = 0,
        y      = 6,
        width  = 12,
        height = 6,
        properties = {
          metrics = [
            ["AWS/EC2", "CPUUtilization", { "stat" = "Average", "label" = "EC2 CPU (Avg)" }],
            ["AWS/RDS", "CPUUtilization", { "stat" = "Average", "label" = "RDS CPU (Avg)" }]
          ],
          view   = "timeSeries",
          region = data.aws_region.current.id,
          title  = "💻 Compute & Database Health",
          period = 300
        }
      },
      {
        type   = "metric",
        x      = 12,
        y      = 6,
        width  = 12,
        height = 6,
        properties = {
          metrics = [
            ["AWS/Lambda", "Errors", { "stat" = "Sum", "label" = "Lambda Errors" }],
            ["AWS/Lambda", "Throttles", { "stat" = "Sum", "label" = "Throttles" }]
          ],
          view   = "timeSeries",
          region = data.aws_region.current.id,
          title  = "⚡ Serverless Errors",
          period = 300
        }
      }
    ]
  })
}

resource "aws_ssm_parameter" "config_topic_arn" {
  count       = var.create_global_resources ? 1 : 0
  name        = "/${var.project_name}/global/observability/config_compliance_topic_arn"
  description = "ARN do Topico SNS de Conformidade e Segurança para alarmes centralizados"
  type        = "String"
  value       = aws_sns_topic.config_compliance[0].arn
  tags        = var.tags
}

# =================================================================================
# BUCKETS DE AUDITORIA E CONFIG (Missing Resources)
# =================================================================================

resource "aws_s3_bucket" "audit_logs" {
  count         = var.create_global_resources ? 1 : 0
  bucket        = var.audit_logs_bucket_name
  force_destroy = true
  tags          = var.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_logs" {
  count  = var.create_global_resources ? 1 : 0
  bucket = aws_s3_bucket.audit_logs[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "audit_logs" {
  count  = var.create_global_resources ? 1 : 0
  bucket = aws_s3_bucket.audit_logs[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "audit_logs" {
  count  = var.create_global_resources ? 1 : 0
  bucket = aws_s3_bucket.audit_logs[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "audit_logs_policy" {
  count = var.create_global_resources ? 1 : 0
  statement {
    sid    = "AWSCloudTrailAclCheck"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.audit_logs[0].arn]
  }
  statement {
    sid    = "AWSCloudTrailWrite"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.audit_logs[0].arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_versioning" "config" {
  count  = var.create_global_resources ? 1 : 0
  bucket = aws_s3_bucket.config[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "config" {
  count  = var.create_global_resources ? 1 : 0
  bucket = aws_s3_bucket.config[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "audit_logs" {
  count  = var.create_global_resources ? 1 : 0
  bucket = aws_s3_bucket.audit_logs[0].id
  policy = data.aws_iam_policy_document.audit_logs_policy[0].json
}

resource "aws_s3_bucket" "config" {
  count         = var.create_global_resources ? 1 : 0
  bucket        = var.config_bucket_name
  force_destroy = true
  tags          = var.tags
}

data "aws_iam_policy_document" "config_bucket_policy" {
  count = var.create_global_resources ? 1 : 0
  statement {
    sid    = "AWSConfigBucketPermissionsCheck"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["config.amazonaws.com"]
    }
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.config[0].arn]
  }
  statement {
    sid    = "AWSConfigBucketDelivery"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["config.amazonaws.com"]
    }
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.config[0].arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/Config/*"]
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_policy" "config" {
  count  = var.create_global_resources ? 1 : 0
  bucket = aws_s3_bucket.config[0].id
  policy = data.aws_iam_policy_document.config_bucket_policy[0].json
}

resource "aws_s3_bucket_server_side_encryption_configuration" "config" {
  count  = var.create_global_resources ? 1 : 0
  bucket = aws_s3_bucket.config[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
