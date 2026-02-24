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

var observerCmd = &cobra.Command{
	Use:   "observer",
	Short: "Inicia o Agente Observador (Cloud Watcher)",
	Long:  `Inicia o agente de observabilidade que monitora logs, métricas e custos da AWS em tempo real.`,
	Run:   runObserver,
}

func init() {
	rootCmd.AddCommand(observerCmd)
}

func runObserver(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, "core", "agents", "cloud_watcher.py")

	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		fmt.Printf("❌ Erro: Script do Observador não encontrado em: %s\n", scriptPath)
		os.Exit(1)
	}

	pythonBin := getPythonBinary()

	// FIX: Injeta contexto para monitoramento direcionado
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

	fmt.Println("👁️  Iniciando Observador (Wrapper Go)...")
	if err := c.Run(); err != nil {
		if exitError, ok := err.(*exec.ExitError); ok {
			os.Exit(exitError.ExitCode())
		}
		fmt.Printf("❌ Erro na execução: %v\n", err)
		os.Exit(1)
	}
}
