package custom.encryption

# Garante criptografia em volumes EBS
deny[msg] {
    resource := input.resource
    resource.type == "aws_ebs_volume"

    # Se encrypted não for true (pode ser null/false)
    resource.values.encrypted != true

    msg := sprintf("Volume EBS '%s' deve ter criptografia habilitada (encrypted = true).", [resource.name])
}

# Garante criptografia em RDS
deny[msg] {
    resource := input.resource
    resource.type == "aws_db_instance"
    resource.values.storage_encrypted != true
    msg := sprintf("Banco de dados RDS '%s' deve ter storage_encrypted = true.", [resource.name])
}
