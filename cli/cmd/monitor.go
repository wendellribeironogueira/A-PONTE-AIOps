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

var monitorCmd = &cobra.Command{
	Use:   "monitor",
	Short: "Inicia o Dashboard TUI de Observabilidade",
	Long:  `Inicia o painel de controle interativo (TUI) com métricas de AWS, Docker e Segurança.`,
	Run:   runMonitor,
}

func init() {
	rootCmd.AddCommand(monitorCmd)
}

func runMonitor(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, "core", "tools", "tui", "dashboard.py")

	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		fmt.Printf("❌ Erro: Script do Dashboard não encontrado em: %s\n", scriptPath)
		os.Exit(1)
	}

	pythonBin := getPythonBinary()

	// FIX: Injeta contexto para que o dashboard saiba qual projeto monitorar
	if project, err := core.GetContext(); err == nil && project != "" && project != "home" {
		projData, _ := core.GetProject(project)
		injectProjectEnv(project, projData)
	}

	cmdArgs := []string{scriptPath}
	cmdArgs = append(cmdArgs, args...)

	c := exec.Command(pythonBin, cmdArgs...)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin

	c.Env = getPythonEnv(root)

	fmt.Println("📊 Iniciando Dashboard A-PONTE...")
	if err := c.Run(); err != nil {
		if exitError, ok := err.(*exec.ExitError); ok {
			os.Exit(exitError.ExitCode())
		}
		fmt.Printf("❌ Erro na execução: %v\n", err)
		os.Exit(1)
	}
}
