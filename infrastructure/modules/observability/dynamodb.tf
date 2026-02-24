resource "aws_dynamodb_table" "events_dedup" {
  count        = var.create_global_resources ? 1 : 0
  name         = "a-ponte-events-dedup"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "EventID"

  attribute {
    name = "EventID"
    type = "S"
  }

  ttl {
    attribute_name = "ExpirationTime"
    enabled        = true
  }

  tags = var.tags
}

resource "aws_dynamodb_table" "ai_history" {
  count        = var.create_global_resources ? 1 : 0
  name         = "a-ponte-ai-history"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ProjectName"
  range_key    = "Timestamp"

  attribute {
    name = "ProjectName"
    type = "S"
  }

  attribute {
    name = "Timestamp"
    type = "S"
  }

  ttl {
    attribute_name = "ExpirationTime"
    enabled        = true
  }

  tags = var.tags
}

resource "aws_dynamodb_table" "registry" {
  count        = var.create_global_resources ? 1 : 0
  name         = "a-ponte-registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ProjectName"

  attribute {
    name = "ProjectName"
    type = "S"
  }

  tags = var.tags
}
