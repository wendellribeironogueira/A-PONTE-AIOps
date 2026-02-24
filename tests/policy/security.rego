package security

import future.keywords.in

# 1. Exigir Permissions Boundary em Roles (Específico do A-PONTE)
# Isso garante que nenhuma Role criada escape do limite de permissões da conta.
deny[msg] {
    resource := input.resource_changes[_]
    resource.type == "aws_iam_role"
    # Ignora a role de serviço vinculada ao Organizations se existir
    not contains(resource.address, "OrganizationAccountAccessRole")
    not resource.change.after.permissions_boundary
    msg := sprintf("HIGH: IAM Role '%s' must have a Permissions Boundary attached.", [resource.address])
}

# 2. Validar Tags Obrigatórias (Governança)
deny[msg] {
    resource := input.resource_changes[_]
    resource.type in ["aws_s3_bucket", "aws_iam_role", "aws_dynamodb_table", "aws_instance"]

    required_tags := {"Project", "Environment", "ManagedBy"}
    provided_tags := {key | resource.change.after.tags[key]}

    missing := required_tags - provided_tags
    count(missing) > 0

    msg := sprintf("MEDIUM: Resource '%s' is missing required tags: %v", [resource.address, missing])
}
