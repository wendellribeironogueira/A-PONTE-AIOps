package cmd

import (
	"context"
	"os"
	"os/signal"

	"github.com/spf13/cobra"
)

// rootCmd represents the base command when called without any subcommands
var rootCmd = &cobra.Command{
	Use:   "aponte",
	Short: "CLI de Governança A-PONTE",
	Long: `Ferramenta de linha de comando para orquestração e governança
da plataforma A-PONTE.

Módulos Principais:
  - Project: Gerenciamento de Multi-Tenancy e Contextos
  - Infra: Orquestração de Containers (Docker/MCP)
  - TF: Wrapper inteligente para Terraform/Terragrunt com Auto-Healing
  - Security: Pipeline de segurança (Checkov, TFSec, Trivy, Prowler)
  - AI: Agentes inteligentes (Arquiteto, Doctor, Sentinel)
  - Git: Automação e auditoria de repositórios

Arquitetura Híbrida: Go (CLI/Wrapper) + Python (Core Logic).`,
}

// Execute adds all child commands to the root command and sets flags appropriately.
func Execute() {
	// Hard Enforcement: Se executado fora do wrapper (sem Session ID) e sem contexto explícito,
	// força contexto neutro para evitar leitura acidental de estado persistido (default).
	if os.Getenv("APONTE_SESSION_ID") == "" && os.Getenv("TF_VAR_project_name") == "" {
		_ = os.Setenv("TF_VAR_project_name", "home")
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()

	if err := rootCmd.ExecuteContext(ctx); err != nil {
		os.Exit(1)
	}
}
