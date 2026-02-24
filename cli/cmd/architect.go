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

var architectCmd = &cobra.Command{
	Use:   "architect",
	Short: "Inicia o Arquiteto Virtual (Chat)",
	Long:  `Inicia o agente de IA Arquiteto para design de infraestrutura e operações.`,
	Run:   runArchitect,
}

func init() {
	rootCmd.AddCommand(architectCmd)
}

func runArchitect(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, "core", "agents", "architect.py")

	// Verifica se o script existe
	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		fmt.Printf("❌ Erro: Script do Arquiteto não encontrado em: %s\n", scriptPath)
		os.Exit(1)
	}

	// Detecta Python (venv ou sistema)
	pythonBin := getPythonBinary()

	// FIX: Injeta contexto se estiver dentro de um projeto ativo
	if project, err := core.GetContext(); err == nil && project != "" && project != "home" {
		projData, _ := core.GetProject(project)
		injectProjectEnv(project, projData)
		fmt.Printf("🏗️  Contexto carregado: %s (%s)\n", project, os.Getenv("TF_VAR_environment"))
	}

	// Prepara execução
	cmdArgs := []string{scriptPath}
	cmdArgs = append(cmdArgs, args...)

	c := exec.Command(pythonBin, cmdArgs...)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin // Importante para interatividade

	// Injeta variáveis de ambiente críticas para o funcionamento do Agente
	c.Env = getPythonEnv(root)

	fmt.Println("🤖 Iniciando Arquiteto Virtual...")
	if err := c.Run(); err != nil {
		// Se for exit code, propaga o código do script
		if exitError, ok := err.(*exec.ExitError); ok {
			os.Exit(exitError.ExitCode())
		}
		fmt.Printf("❌ Erro na execução: %v\n", err)
		os.Exit(1)
	}
}
