# Contribuindo para A-PONTE

Primeiro; Obrigado por considerar contribuir para o **A-PONTE**! É gente como você que faz a comunidade de tecnologia Brasileira ser respeitada mundialmente.

## 📍 Código de Conduta

Este projeto e todos os seus participantes estão sob o Código de Conduta. Ao participar, espera-se que você mantenha este código.

## 🛡️ Filosofia de Segurança

O **A-PONTE** não é apenas um script de automação; é uma ferramenta de **Segurança e Governança**.

- **Não diminua a segurança:** PRs que removem criptografia, abrem portas desnecessárias ou concedem permissões excessivas (ex: `Action: "*"`) serão rejeitados.
- **Respeite os ADRs:** Leia a pasta `/docs`. Mudanças arquiteturais devem vir acompanhadas de uma atualização ou novo ADR.

## 🔧 Como Contribuir

1.  Faça um Fork do repositório.
2.  Crie uma Branch para sua feature (`git checkout -b feature/MinhaFeature`).
3.  Commit suas mudanças (`git commit -m 'Add: Nova funcionalidade de auditoria'`).
4.  Push para a Branch (`git push origin feature/MinhaFeature`).
5.  Abra um Pull Request.

### Padrões de Desenvolvimento

#### Terraform

- Execute `terraform fmt` antes de comitar.
- Use `snake_case` para nomes de recursos e variáveis.
- Todo novo recurso deve ter tags (use a variável `var.tags`).

### Testes

Antes de enviar o PR, garanta que os testes de segurança e política estão passando:

```bash
# Validação de sintaxe e configuração
aponte tf validate

# Scan de segurança (Checkov)
checkov -d .
```

## 🐛 Reportando Bugs

Use a aba de Issues do GitHub. Seja detalhado:

- Qual o sistema operacional?
- Qual a versão do Terraform/AWS CLI?
- Passos para reproduzir o erro.
- Logs (remova informações sensíveis!).

---

> _"Gente de dentro sabe fazer as coisas."_
