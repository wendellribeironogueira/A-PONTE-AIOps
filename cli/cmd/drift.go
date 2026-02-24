package cmd

import (
	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/spf13/cobra"
)

var driftCmd = &cobra.Command{
	Use:   "drift",
	Short: "Detecta divergências na infraestrutura (Drift)",
}

var driftDetectCmd = &cobra.Command{
	Use:   "detect [project]",
	Short: "Verifica se a infraestrutura real difere do código",
	Args:  cobra.MaximumNArgs(1),
	Run:   runDriftDetect,
}

var driftFixCmd = &cobra.Command{
	Use:   "fix [project]",
	Short: "Corrige divergências aplicando a configuração (Apply)",
	Args:  cobra.MaximumNArgs(1),
	Run:   runDriftFix,
}

func init() {
	rootCmd.AddCommand(driftCmd)
	driftCmd.AddCommand(driftDetectCmd)
	driftCmd.AddCommand(driftFixCmd)
}

func runDriftDetect(cmd *cobra.Command, args []string) {
	project := resolveProjectContext(args)
	checkProjectAndExitIfHome(project, "drift detect")

	root := utils.GetProjectRoot()
	projectDir := filepath.Join(root, resolveTfDir(project))

	// 1. Carrega metadados do projeto
	projData, err := core.GetProject(project)
	if err != nil {
		// Apenas loga aviso em debug, drift deve tentar rodar mesmo assim
	}

	// 2. Injeta variáveis de contexto
	injectProjectEnv(project, projData)

	fmt.Printf("🔍 Verificando Drift em %s...\n", project)

	// Executa terragrunt plan -detailed-exitcode
	// Exit Code 0 = Succeeded, diff is empty (no changes)
	// Exit Code 1 = Error
	// Exit Code 2 = Succeeded, there is a diff
	c := execMCPWithProjectEnv(projectDir, "terragrunt", "plan", "-detailed-exitcode", "-input=false", "-lock=false")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		// Verifica exit code
		if exitErr, ok := err.(*exec.ExitError); ok && exitErr.ExitCode() == 2 {
			fmt.Println("⚠️  Drift Detectado!")
			os.Exit(2) // Repassa o código 2 para o Sentinel
		}
		fmt.Printf("❌ Erro na verificação: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("✅ Infraestrutura sincronizada.")
}

func runDriftFix(cmd *cobra.Command, args []string) {
	project := resolveProjectContext(args)
	checkProjectAndExitIfHome(project, "drift fix")

	// Reutiliza a lógica de injeção de contexto do Detect/Deploy
	projData, _ := core.GetProject(project)
	injectProjectEnv(project, projData)

	fmt.Printf("🛠️  Iniciando Correção de Drift (Apply) em %s...\n", project)

	root := utils.GetProjectRoot()
	projectDir := filepath.Join(root, resolveTfDir(project))

	c := execMCPWithProjectEnv(projectDir, "terragrunt", "apply", "--terragrunt-source-update")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin

	if err := c.Run(); err != nil {
		fmt.Printf("❌ Falha na correção: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("✅ Drift corrigido com sucesso!")
}
