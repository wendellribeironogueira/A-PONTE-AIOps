# Snippet: Bucket S3 Seguro (Padrão A-PONTE)
# Variáveis necessárias: var.project_name, var.environment, var.tags

resource "aws_s3_bucket" "this" {
  # Naming convention: project-env-name-accountid
  bucket = lower("${var.project_name}-${var.environment}-assets-${data.aws_caller_identity.current.account_id}")
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
