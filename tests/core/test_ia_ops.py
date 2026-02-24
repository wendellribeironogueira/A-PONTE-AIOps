#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

# Configuração de Paths para encontrar os módulos do projeto
# Ajuste: .parent.parent.parent para sair de tests/core/ e chegar na raiz A-PONTE
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# Importação real do módulo (Sem Mocks)
from core.lib import toolbelt


class TestSecurityAuditor(unittest.TestCase):

    def test_sanitize_hcl_quotes(self):
        """Testa se aspas simples são convertidas para duplas (padrão HCL)."""
        code = "resource 'aws_s3_bucket' 'example' {}"
        expected = 'resource "aws_s3_bucket" "example" {}'
        self.assertEqual(toolbelt.sanitize_hcl(code), expected)

    def test_sanitize_hcl_hallucinations(self):
        """Testa se atributos inventados pela IA são removidos."""
        code = """
        resource "aws_instance" "web" {
            ami = "ami-123456"
            allowVisibility = true
            instance_type = "t2.micro"
        }
        """
        sanitized = toolbelt.sanitize_hcl(code)
        self.assertNotIn("allowVisibility", sanitized)
        self.assertIn('ami = "ami-123456"', sanitized)

    def test_sanitize_hcl_comments(self):
        """Testa se comentários são preservados e não alterados."""
        code = "# This is a 'comment' with quotes"
        self.assertEqual(toolbelt.sanitize_hcl(code), code)


if __name__ == "__main__":
    unittest.main()
