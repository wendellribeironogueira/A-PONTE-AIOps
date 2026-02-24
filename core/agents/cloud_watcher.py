#!/usr/bin/env python3
import sys
import time
import re
import json
import contextlib
import io
from pathlib import Path
from datetime import datetime

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, DataTable, Static, Label
    from textual.containers import Container, Grid
    from textual.binding import Binding
except ImportError:
    print("Erro: A biblioteca 'textual' não está instalada. Execute: pip install textual")
    sys.exit(1)

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common
from core.lib import aws
from core.services import llm_gateway as llm_client
from core.domain import prompts as system_context

def sanitize_log(text: str) -> str:
    """Remove credenciais e dados sensíveis dos logs antes de processar."""
    # Mascara AWS Access Keys (AKIA/ASIA...)
    text = re.sub(r'(AKIA|ASIA)[A-Z0-9]{16}', '***AWS_KEY***', text)
    # Mascara padrões genéricos de segredos (heuristicamente)
    text = re.sub(r'(?i)(secret|token|password|key)\s*[:=]\s*["\']?([a-zA-Z0-9/+_\-]{20,})["\']?', r'\1: ***SECRET***', text)
    return text

class ObserverApp(App):
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-rows: 2fr 1fr;
        grid-columns: 1fr 1fr;
        grid-gutter: 1;
    }

    #logs_container {
        column-span: 2;
        border: solid green;
        background: $surface;
    }

    #alarms_container {
        border: solid red;
        background: $surface;
    }

    #ai_container {
        border: solid magenta;
        background: $surface;
    }

    .box-title {
        background: $accent;
        color: $text;
        padding: 0 1;
        text-align: center;
        text-style: bold;
    }

    DataTable {
        height: 1fr;
    }

    #ai_content {
        padding: 1;
        height: 1fr;
        overflow-y: scroll;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("r", "refresh", "Atualizar Agora"),
    ]

    def __init__(self, project_name):
        super().__init__()
        self.project_name = project_name
        self.ai_state = {
            "last_check": 0,
            "analysis": "Inicializando análise cognitiva...",
            "interval": 30
        }

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id="logs_container"):
            yield Label(f"☁️  CloudTrail & Logs: {self.project_name}", classes="box-title")
            yield DataTable(id="logs_table")

        with Container(id="alarms_container"):
            yield Label("🚨 Active Alarms", classes="box-title")
            yield DataTable(id="alarms_table")

        with Container(id="ai_container"):
            yield Label("🧠 Observer AI Insight", classes="box-title")
            yield Static("Aguardando dados...", id="ai_content")

        yield Footer()

    def on_mount(self):
        self.title = f"A-PONTE Observer - {self.project_name}"

        logs_table = self.query_one("#logs_table", DataTable)
        logs_table.add_columns("Time", "Service", "Message")
        logs_table.cursor_type = "row"
        logs_table.zebra_stripes = True

        alarms_table = self.query_one("#alarms_table", DataTable)
        alarms_table.add_columns("Time", "Alarm", "State")
        alarms_table.cursor_type = "row"

        # Initial fetch
        self.action_refresh()
        # Periodic fetch
        self.set_interval(10, self.action_refresh)

    def action_refresh(self):
        self.run_worker(self._fetch_data, thread=True)

    def _fetch_data(self):
        # Fetch Logs
        new_logs_rows = []
        current_logs_text = []

        try:
            logs = aws.get_session().client("logs")
            log_group = f"aws-cloudtrail-logs-{self.project_name}"

            events = logs.filter_log_events(
                logGroupName=log_group,
                limit=10,
                interleaved=True
            )
            for e in events.get("events", []):
                ts = datetime.fromtimestamp(e['timestamp']/1000).strftime('%H:%M:%S')
                msg = e['message'][:100]
                new_logs_rows.append((ts, "CloudTrail (CW)", msg))
                current_logs_text.append(e['message'])
        except Exception as e:
            # Fallback: Se o Log Group não existir (comum em setups novos), usa a API do CloudTrail
            if "ResourceNotFoundException" in str(e):
                try:
                    ct = aws.get_session().client("cloudtrail")
                    # Busca os últimos 10 eventos de gestão (Free Tier)
                    events = ct.lookup_events(MaxResults=10)
                    for e in events.get("Events", []):
                        ts = e['EventTime'].strftime('%H:%M:%S')
                        msg = f"{e.get('EventName')} | {e.get('Username')}"
                        new_logs_rows.append((ts, "CloudTrail (API)", msg))
                        current_logs_text.append(json.dumps(e, default=str))
                except Exception as ct_e:
                    new_logs_rows.append((datetime.now().strftime('%H:%M:%S'), "System", f"Erro CloudTrail API: {str(ct_e)[:50]}"))
            else:
                new_logs_rows.append((datetime.now().strftime('%H:%M:%S'), "System", f"Erro Logs: {str(e)[:50]}"))

        # Fetch Alarms
        new_alarms_rows = []
        current_alarms_text = []
        try:
            cw = aws.get_session().client("cloudwatch")
            alarms = cw.describe_alarms(StateValue='ALARM')
            for a in alarms.get('MetricAlarms', []):
                if not a['AlarmName'].startswith(self.project_name):
                    continue
                ts = datetime.now().strftime('%H:%M:%S')
                new_alarms_rows.append((ts, a['AlarmName'], a['StateReason'][:50]))
                current_alarms_text.append(f"{a['AlarmName']}: {a['StateReason']}")
        except Exception as e:
            new_alarms_rows.append((datetime.now().strftime('%H:%M:%S'), "System", f"Erro Alarms: {str(e)[:50]}"))

        # Update UI
        self.call_from_thread(self._update_tables, new_logs_rows, new_alarms_rows)

        # AI Analysis (if needed)
        self._run_ai_analysis(current_logs_text, current_alarms_text)

    def _update_tables(self, logs_rows, alarms_rows):
        logs_table = self.query_one("#logs_table", DataTable)
        logs_table.clear()
        for row in logs_rows:
            logs_table.add_row(*row)

        alarms_table = self.query_one("#alarms_table", DataTable)
        alarms_table.clear()
        for row in alarms_rows:
            alarms_table.add_row(*row)

    def _run_ai_analysis(self, logs, alarms):
        now = time.time()
        if now - self.ai_state["last_check"] < self.ai_state["interval"]:
            return

        # Logic from original analyze_health
        has_errors = any("ERROR" in l for l in logs)
        if not alarms and not has_errors:
            analysis = "✅ Sistema Saudável. Nenhuma anomalia detectada."
        else:
            sanitized_logs = [sanitize_log(l) for l in logs]
            prompt = f"""
            {system_context.APONTE_CONTEXT}
            Atue como um SRE Sênior (Observer Agent).
            ALARMES: {alarms}
            LOGS: {sanitized_logs}
            Diagnóstico curto (1 frase):
            """
            try:
                # Protege a TUI contra prints do backend e aumenta timeout
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    analysis = llm_client.generate(prompt, verbose=False, timeout=30, provider="ollama")
            except Exception as e:
                analysis = f"Erro na IA: {str(e)[:100]}..."

        self.ai_state["last_check"] = now
        self.ai_state["analysis"] = analysis
        self.call_from_thread(self._update_ai_widget, analysis)

    def _update_ai_widget(self, content):
        self.query_one("#ai_content", Static).update(content)

def main():
    project = common.read_context()
    if project == "home":
        common.log_error("Selecione um projeto para monitorar.")
        return

    # Garante que o servidor de IA esteja rodando
    if not llm_client.is_available():
        provider = getattr(llm_client, "AI_PROVIDER", "ollama")
        if provider == "ollama":
            common.console.print(f"[yellow]Iniciando servidor de IA ({provider})...[/]")
        llm_client.start_server()

    app = ObserverApp(project)
    try:
        app.run()
    finally:
        llm_client.stop_server()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
