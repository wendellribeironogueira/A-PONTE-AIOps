#!/usr/bin/env python3
import sys
import boto3
import json
import datetime
import os
from pathlib import Path

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common
from core.lib import aws

def enable_break_glass(project_name):
    common.console.rule("[bold red]🚨 A-PONTE Break Glass Protocol[/]")

    if not project_name or project_name == "home":
        common.log_error("Selecione um projeto para ativar o acesso de emergência.")
        return

    # Tenta encontrar a role de break glass
    account_id = aws.get_account_id()
    role_name = f"{project_name}-support-break-glass"
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    common.console.print(f"🔍 Verificando role de emergência: [cyan]{role_arn}[/]")

    try:
        iam = aws.get_client("iam")
        iam.get_role(RoleName=role_name)
    except Exception:
        common.log_error(f"Role de Break Glass não encontrada para {project_name}.")
        common.console.print("[dim]Verifique se 'create_break_glass_role = true' no terraform.[/dim]")
        return

    common.console.print("\n[bold yellow]⚠️  ATENÇÃO: Este acesso será auditado e notificado.[/]")
    if not common.require_confirmation("Deseja assumir privilégios de ADMINISTRADOR?"):
        return

    # Gera comando para assumir a role
    cmd = f'export $(printf "AWS_ACCESS_KEY_ID=%s AWS_SECRET_ACCESS_KEY=%s AWS_SESSION_TOKEN=%s" $(aws sts assume-role --role-arn {role_arn} --role-session-name BreakGlass-{project_name} --query "Credentials.[AccessKeyId,SecretAccessKey,SessionToken]" --output text))'

    # Notificação SNS para Auditoria de Segurança
    try:
        session = aws.get_session()
        region = session.region_name
        # Tenta inferir o tópico de segurança padrão da plataforma
        topic_arn = f"arn:aws:sns:{region}:{account_id}:a-ponte-security-alerts"

        sns = session.client("sns")
        sns.publish(
            TopicArn=topic_arn,
            Subject=f"🚨 BREAK GLASS ATIVADO: {project_name}",
            Message=f"ALERTA DE SEGURANÇA\n\nUsuário: {aws.get_current_user()}\nProjeto: {project_name}\nRole Assumida: {role_arn}\n\nO protocolo de acesso emergencial (Break Glass) foi ativado. Verifique a legitimidade desta operação imediatamente."
        )
        common.log_success("Evento de auditoria registrado e notificação SNS enviada.")
    except Exception as e:
        common.log_warning(f"Evento registrado localmente, mas falha ao enviar SNS: {e}")

    # Agendamento de Revogação Automática (ADR-007 Safety Net)
    revocation_scheduled = False
    try:
        scheduler = aws.get_client("scheduler")
        # Agenda para 1 hora a partir de agora (UTC)
        now = datetime.datetime.now(datetime.timezone.utc)
        run_time = now + datetime.timedelta(hours=1)
        # Formato at(yyyy-mm-ddThh:mm:ss)
        schedule_expression = f"at({run_time.strftime('%Y-%m-%dT%H:%M:%S')})"

        # Cria agendamento One-Time que se autodestrói após execução
        scheduler.create_schedule(
            Name=f"BreakGlassRevoke-{project_name}-{int(now.timestamp())}",
            ScheduleExpression=schedule_expression,
            Target={
                'Arn': f"arn:aws:lambda:{aws.get_region()}:{account_id}:function:aponte-break-glass-cleanup",
                'RoleArn': f"arn:aws:iam::{account_id}:role/service-role/AponteSchedulerRole",
                'Input': json.dumps({"ProjectName": project_name, "RoleArn": role_arn, "Action": "Revoke"})
            },
            FlexibleTimeWindow={'Mode': 'OFF'},
            ActionAfterCompletion='DELETE'
        )
        common.log_success("Safety Net: Revogação automática agendada para daqui a 1 hora.")
        revocation_scheduled = True
    except Exception as e:
        common.log_warning(f"Falha ao configurar revogação automática (EventBridge): {e}")

        # FAIL-SAFE: Se a rede de segurança falhar, nega o acesso a menos que forçado.
        if os.getenv("FORCE_BREAK_GLASS") != "true":
            common.console.print("\n[bold red]⛔ ACESSO NEGADO (Safety Net Failed)[/]")
            common.console.print("Não foi possível agendar a revogação automática. Por segurança, as credenciais não serão exibidas.")
            common.console.print("Para ignorar (RISCO ALTO), execute com: [white]export FORCE_BREAK_GLASS=true[/]")
            return
        else:
            common.console.print("[bold red]⚠️  ATENÇÃO CRÍTICA: A revogação automática falhou, mas o acesso foi forçado via variável de ambiente. Você DEVE desativar este acesso manualmente![/]")

    # Exibe as credenciais APENAS após tentar registrar a auditoria e safety nets
    common.console.print("\n[green]✅ Acesso Autorizado. Execute o comando abaixo no seu terminal:[/]\n")
    common.console.print(f"[bold white on black]{cmd}[/]")
    common.console.print("\n[dim]Para sair, feche o terminal ou limpe as variáveis de ambiente.[/dim]")

def disable_break_glass():
    common.console.rule("[bold green]🛡️  Desativando Break Glass[/]")
    common.console.print("Para desativar, limpe suas variáveis de ambiente:")
    common.console.print("\n[bold white on black]unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN[/]")
    common.log_success("Sessão encerrada.")

def main():
    if len(sys.argv) < 2:
        print("Uso: break_glass.py <enable|disable> [project]")
        return

    action = sys.argv[1]

    if action == "enable":
        project = os.getenv("TF_VAR_project_name")
        if len(sys.argv) > 2:
            project = sys.argv[2]
        enable_break_glass(project)
    elif action == "disable":
        disable_break_glass()

if __name__ == "__main__":
    main()
