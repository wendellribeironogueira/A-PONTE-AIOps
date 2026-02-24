# 👋 Guia de Offboarding de Projetos

Este guia descreve o processo seguro para desativar e remover projetos da plataforma **A-PONTE**.

---

## 1. Checklist de Desativação

- [ ] Confirmar com stakeholders que o serviço pode ser desligado.
- [ ] Verificar se há dados que precisam de backup final (Snapshot RDS/S3).
- [ ] Garantir acesso de `Administrator` ou `BreakGlass` para destruição.

---

## 2. Destruição de Infraestrutura (Nuvem)

O primeiro passo é remover os recursos da AWS para cessar a cobrança.

**Comando:**

```bash
aponte tf destroy
# ou
aponte project destroy <nome-do-projeto>
```

**O que acontece:**

1. O Terragrunt executa `destroy` em todos os módulos.
2. **Backup Automático:** Antes de destruir, o sistema tenta criar um backup final do estado.
3. Recursos como EC2, RDS, VPC são terminados.
4. **Exceção:** O Bucket S3 de Logs e Estado pode ter proteção contra deleção (`force_destroy = false`). Se falhar, esvazie o bucket manualmente via console.

---

## 3. Limpeza Local (Máquina do Analista)

Após destruir a nuvem, remova as configurações locais para manter seu ambiente limpo.

**Comando:**

```bash
aponte project detach
```

**O que acontece:**

1. Remove o arquivo `projects/<nome>.yml`.
2. Remove o vínculo no arquivo `.repos`.
3. Limpa caches locais (`.terragrunt-cache`).

---

## 4. Arquivamento (Opcional)

Se o projeto for apenas pausado, não execute o passo 3. Mantenha os arquivos de configuração no Git. Para reativar no futuro, basta rodar `aponte deploy project` novamente.
