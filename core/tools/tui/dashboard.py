#!/usr/bin/env python3
import json
from datetime import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from textual import work
    from textual.app import App, ComposeResult
    from textual.containers import Container, Grid
    from textual.widgets import Footer, Header, Label, RichLog, Static
except ImportError:
    print("❌ A biblioteca 'textual' é necessária. Instale com: pip install textual")
    sys.exit(1)

# Importa módulos locais
# Adiciona a raiz do projeto ao path para permitir imports absolutos de 'core'
project_root = Path(__file__).parents[3].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import aws
from core.lib import utils as common


class APonteDashboard(App):
    """Dashboard de Observabilidade A-PONTE."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 3 4;
        grid-rows: 1fr 1fr 3 2fr;
        grid-columns: 1fr 1fr 1fr;
        grid-gutter: 1;
        padding: 1;
    }

    .box {
        background: $surface;
        padding: 1;
        border: solid $primary;
    }

    .box-title {
        text-align: center;
        text-style: bold;
        color: $text-muted;
        width: 100%;
        background: $surface-lighten-1;
        margin-bottom: 1;
    }

    .content-area {
        content-align: center middle;
        height: 1fr;
    }

    /* Row 1: AWS Core (Data-Driven) */
    #panel-aws-id { border: wide blue; }
    #panel-aws-health { border: wide red; }
    #panel-aws-cost { border: wide green; }

    /* Row 2: Context & Ops */
    #panel-project { border: wide cyan; }
    #panel-security { border: wide orange; }
    #panel-local { border: wide yellow; }

    /* Row 3: AI Insight */
    #panel-ai {
        column-span: 3;
        height: 3;
        border: solid magenta;
        background: $surface-darken-1;
        content-align: center middle;
    }

    /* Row 4: Logs */
    #log-view {
        column-span: 3;
        height: 100%;
        border: solid $secondary;
    }
    """

    TITLE = "A-PONTE AWS Observability Hub"
    SUB_TITLE = "Data-Driven Operations Center"
    last_log_size = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        # Row 1: AWS Focus
        with Container(classes="box", id="panel-aws-id"):
            yield Label("🆔 AWS Identity", classes="box-title")
            yield Label("Loading...", id="aws-id-content", classes="content-area")

        with Container(classes="box", id="panel-aws-health"):
            yield Label("❤️ AWS Health", classes="box-title")
            yield Label("Loading...", id="aws-health-content", classes="content-area")

        with Container(classes="box", id="panel-aws-cost"):
            yield Label("💸 AWS FinOps", classes="box-title")
            yield Label("Loading...", id="aws-cost-content", classes="content-area")

        # Row 2: Operational Context
        with Container(classes="box", id="panel-project"):
            yield Label("📂 Project Context", classes="box-title")
            yield Label("Loading...", id="project-content", classes="content-area")

        with Container(classes="box", id="panel-security"):
            yield Label("🛡️ Security Posture", classes="box-title")
            yield Label("Loading...", id="security-content", classes="content-area")

        with Container(classes="box", id="panel-local"):
            yield Label("🐳 Local Runtime", classes="box-title")
            yield Label("Loading...", id="local-content", classes="content-area")

        # Row 3: AI & Logs
        with Container(classes="box", id="panel-ai"):
            yield Label("🧠 AI Insight: Monitoramento ativo.", id="ai-content")

        yield RichLog(id="log-view", highlight=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        self.log_file = common.get_project_root() / "logs" / "system.log"
        self.query_one(RichLog).write(
            f"[bold green]✔ Monitoramento Iniciado: {self.log_file}[/]"
        )

        # Timers de atualização
        self.set_interval(5, self.update_metrics)
        self.set_interval(1, self.tail_logs)
        self.set_interval(300, self.sync_dojo)
        self.update_metrics()
        self.sync_dojo()

    @work(exclusive=True, thread=True)
    def update_metrics(self):
        log = self.query_one(RichLog)
        # 1. Cloud Context
        # Lê do arquivo JSON gerado pelo produtor (snapshot_metrics.py)
        state_file = common.get_project_root() / "logs" / "observability_state.json"
        data = {}

        try:
            if state_file.exists():
                with open(state_file, "r") as f:
                    data = json.load(f)
        except Exception:
            pass

        # Parse AWS Data
        aws_data = data.get("aws", {})
        account = aws_data.get("account", "Unknown")
        region = aws_data.get("region", "sa-east-1")
        status = aws_data.get("status", "disconnected")

        if status != "connected":
             account = f"[red]{account} (Offline)[/]"

        aws_info = f"[bold]Account:[/]\n{account}\n\n[bold]Region:[/]\n{region}"
        self.query_one("#aws-id-content", Label).update(aws_info)

        # Project Info
        project_name = data.get("project", {}).get("name", common.read_context())

        # Git Status
        git_info = "[dim]Git: N/A[/dim]"
        try:
            # Branch
            branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
            # Dirty check
            status = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()

            if status:
                git_state = "[bold red]*DIRTY*[/]"
            else:
                git_state = "[green]CLEAN[/]"

            git_info = f"Git: [bold cyan]{branch}[/] ({git_state})"
        except Exception:
            pass

        project_info = f"[bold]Project:[/]\n{project_name}\n\n{git_info}"
        self.query_one("#project-content", Label).update(project_info)

        # CloudWatch Alarms
        alarms_data = aws_data.get("alarms", {})
        if "error" in alarms_data:
            alarms_status = f"[red]Error: {alarms_data['error']}[/]"
        else:
            count = alarms_data.get("count", 0)
            if count == 0:
                alarms_status = "[bold green]✔ All Systems Operational[/]"
            else:
                alarms_status = f"[bold red blink]🚨 {count} ALARMS ACTIVE[/]"

        # Timestamp do Snapshot
        ts = data.get("timestamp", "")
        if ts:
            # Calcula idade do dado
            try:
                delta = datetime.now() - datetime.fromisoformat(ts)
                if delta.total_seconds() > 120:
                    alarms_status += f"\n[dim yellow](Dados antigos: {int(delta.total_seconds())}s)[/]"
            except:
                pass

        self.query_one("#aws-health-content", Label).update(alarms_status)

        # Docker Stats (Real-time)
        docker_summary = "[dim]Docker offline[/dim]"
        total_cpu = 0.0
        total_mem = 0.0
        active_containers = 0

        try:
            cmd = [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().split("\n")
                active_containers = len(lines)
                for line in lines:
                    parts = line.split("|")
                    if len(parts) == 3:
                        try:
                            total_cpu += float(parts[1].replace("%", ""))
                        except:
                            pass
                        try:
                            total_mem += float(parts[2].replace("%", ""))
                        except:
                            pass

                docker_summary = f"[bold]All Containers:[/]\n{active_containers} Running\n\n[bold]System Load:[/]\nCPU: [yellow]{total_cpu:.1f}%[/]\nMem: [blue]{total_mem:.1f}%[/]"
            elif res.returncode != 0:
                err = res.stderr.strip() or "Exit Code Non-Zero"
                if "permission denied" in err.lower():
                    docker_summary = "[bold red]🚫 Permission Denied[/]"
                else:
                    docker_summary = "[bold red]Docker Error[/]"
        except Exception:
            pass

        self.query_one("#local-content", Label).update(docker_summary)

        # 2. Security (DefectDojo + CloudWatch) - LÓGICA DO DOJO DEVE SER SUBISTITUIDA POR ABORDAGEM CUSTOM - DOJO FOI REMOVIDO DO PROJEOT
        sec_data = data.get("security", {}).get("defectdojo", {})
        status = sec_data.get("status")

        if status == "connected":
            crit = sec_data.get("critical", 0)
            high = sec_data.get("high", 0)
            med = sec_data.get("medium", 0)
            dojo_stats = f"[bold red]Critical: {crit}[/]\n[bold orange]High:     {high}[/]\n[bold yellow]Medium:   {med}[/]"
        elif "error" in sec_data:
            dojo_stats = f"[yellow]Dojo Error: {sec_data['error']}[/]"
        else:
            dojo_stats = "[yellow]⚠️  Config Required[/]\n[dim]Export DEFECTDOJO_URL/TOKEN[/]"

        self.query_one("#security-content", Label).update(dojo_stats)

        # 3. Atualiza Budget (Real via AWS Budgets)
        finops = aws_data.get("finops", {})
        if "error" in finops:
            budget_info = "[dim]Budget info unavailable[/dim]"
        else:
            actual = finops.get("actual", 0.0)
            limit = finops.get("limit", 0.0)
            percent = finops.get("percent", 0.0)
            budget_info = f"[bold]Spend:[/]\n${actual:.2f} / ${limit:.0f}\n\n[bold]Status:[/]\n{percent:.1f}% Used"

        self.query_one("#aws-cost-content", Label).update(budget_info)

        # 6. Atualiza IA Insight (Lê do DynamoDB ou arquivo local)
        ai_hist = data.get("ai_history", {})
        if ai_hist:
            snippet = ai_hist.get("ErrorSnippet", "")[:50] + "..."
            self.query_one("#ai-content", Label).update(
                f"[bold red]Erro Recente:[/]\n{snippet} - [green]Verifique logs para correção[/]"
            )
        # Fallback local removido em favor da fonte única (snapshot)

    @work(exclusive=True, thread=True)
    def sync_dojo(self):
        """Envia logs locais para o DefectDojo periodicamente."""
        log = self.query_one(RichLog)
        if not os.getenv("DEFECTDOJO_URL") or not os.getenv("DEFECTDOJO_TOKEN"):
            return

        try:
            # Executa comando de exportação (timeout 60s para não encavalar)
            res = subprocess.run(
                ["aponte", "security", "defectdojo"],
                capture_output=True,
                text=True,
                timeout=60,
                env=os.environ.copy()
            )
            if res.returncode == 0:
                log.write("[bold green]🔄 DefectDojo Sync: Relatórios de segurança locais enviados para o Dojo.[/]")
                # Dispara atualização do snapshot para refletir os novos dados no dashboard
                subprocess.run(["aponte", "ops", "snapshot"], capture_output=True)
                self.update_metrics() # Lê o novo JSON
        except Exception as e:
            log.write(f"[red]Dojo Sync Error: {e}[/]")

    def clean_and_format(self, line):
        """Remove códigos ANSI sujos e aplica formatação limpa do Textual."""
        # 1. Remove códigos ANSI (cores de terminal raw que poluem o log)
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        text = ansi_escape.sub("", line).strip()

        # 2. Formatação Visual (Textual Markup) para destaque
        if "[ERROR]" in text:
            return f"[bold red]{text}[/]"
        elif "[WARNING]" in text:
            return f"[bold yellow]{text}[/]"
        elif "SUCCESS" in text or "✅" in text:
            return f"[bold green]{text}[/]"
        return f"[dim]{text}[/]"

    def tail_logs(self):
        """Lê novas linhas do log."""
        if self.log_file.exists():
            try:
                # Otimização: Só lê se o arquivo mudou de tamanho
                current_size = self.log_file.stat().st_size
                if current_size != self.last_log_size:
                    self.last_log_size = current_size
                    with open(self.log_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        self.query_one(RichLog).clear()
                        for line in lines[-20:]:
                            self.query_one(RichLog).write(self.clean_and_format(line))
            except Exception:
                pass  # Ignora erros de leitura (ex: arquivo em uso pelo Windows)


if __name__ == "__main__":
    app = APonteDashboard()
    app.run()
