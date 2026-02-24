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

var sentinelCmd = &cobra.Command{
	Use:   "sentinel",
	Short: "Inicia o Agente Sentinela (Daemon)",
	Long:  `Inicia o daemon de segurança e monitoramento contínuo (Drift, Threat Detection).`,
	Run:   runSentinel,
}

func init() {
	rootCmd.AddCommand(sentinelCmd)
}

func runSentinel(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, "core", "agents", "sentinel.py")

	// Validação de existência do script (Fail Fast)
	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		fmt.Printf("❌ Erro: Script do Sentinela não encontrado em: %s\n", scriptPath)
		os.Exit(1)
	}

	// Detecta Python do ambiente virtual ou sistema
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
	c.Stdin = os.Stdin // Permite interrupção via Ctrl+C

	// Injeta variáveis críticas para o Core Python não quebrar
	c.Env = getPythonEnv(root)

	fmt.Println("🛡️  Iniciando Sentinela (Wrapper Go)...")
	if err := c.Run(); err != nil {
		if exitError, ok := err.(*exec.ExitError); ok {
			os.Exit(exitError.ExitCode())
		}
		fmt.Printf("❌ Erro na execução: %v\n", err)
		os.Exit(1)
	}
}
