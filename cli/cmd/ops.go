package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var opsCmd = &cobra.Command{
	Use:   "ops",
	Short: "Ferramentas de Operação e Qualidade",
}

var pipelineCmd = &cobra.Command{
	Use:   "pipeline",
	Short: "Executa esteira de qualidade (Security + Git Audit)",
	Args:  cobra.MaximumNArgs(1),
	Run:   runPipeline,
}

func init() {
	rootCmd.AddCommand(opsCmd)
	opsCmd.AddCommand(pipelineCmd)
}

func runPipeline(cmd *cobra.Command, args []string) {
	fmt.Println("🚀 Iniciando Pipeline de Qualidade (Quality Gate)...")
	root := utils.GetProjectRoot()

	// FIX: Integração de contexto (SOLID/DRY)
	project := resolveProjectContext(args)
	projData, _ := core.GetProject(project)
	injectProjectEnv(project, projData)

	// 1. Security Audit (Check Mode)
	fmt.Println("\n[1/2] 🛡️  Verificação de Segurança (Infra)...")
	auditScript := filepath.Join(root, "core", "agents", "auditor.py")
	c1 := exec.Command(getPythonBinary(), auditScript, "--mode", "check")
	c1.Stdout = os.Stdout
	c1.Stderr = os.Stderr
	c1.Env = getPythonEnv(root)
	if err := c1.Run(); err != nil {
		fmt.Println("❌ Falha na verificação de segurança.")
		os.Exit(1)
	}

	// 2. Git Audit (Check Mode)
	fmt.Println("\n[2/2] 🐙 Verificação de Alinhamento (Git)...")
	gitScript := filepath.Join(root, "core", "tools", "git_auditor.py")
	c2 := exec.Command(getPythonBinary(), gitScript, "--local", "project", "--mode", "check")
	c2.Stdout = os.Stdout
	c2.Stderr = os.Stderr
	c2.Env = getPythonEnv(root)
	if err := c2.Run(); err != nil {
		fmt.Println("❌ Falha no alinhamento dos repositórios.")
		os.Exit(1)
	}

	fmt.Println("\n✅ Pipeline aprovado com sucesso!")
}
