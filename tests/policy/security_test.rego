package security

test_deny_sg_open_port {
    unsafe_rule := {
        "type": "aws_security_group_rule",
        "change": {
            "after": {
                "cidr_blocks": ["0.0.0.0/0"],
                "from_port": 22,
                "tags": {}
            }
        },
        "address": "module.sg.rule"
    }

    deny["CRITICAL: Security Group Rule 'module.sg.rule' opens port 22 to the world (0.0.0.0/0)."] with input.resource_changes as [unsafe_rule]
}

test_deny_iam_user {
    user := {
        "type": "aws_iam_user",
        "change": {},
        "address": "aws_iam_user.bad"
    }
    deny["CRITICAL: Creation of IAM User 'aws_iam_user.bad' is forbidden. Use IAM Roles and OIDC."] with input.resource_changes as [user]
}
