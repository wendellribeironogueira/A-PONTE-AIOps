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

var doctorCmd = &cobra.Command{
	Use:   "doctor [project]",
	Short: "Diagnostica problemas no sistema (AI Doctor)",
	Long:  `Analisa logs e estado do sistema para identificar e sugerir correções para erros recentes.`,
	Args:  cobra.MaximumNArgs(1),
	Run:   runDoctor,
}

func init() {
	rootCmd.AddCommand(doctorCmd)
}

func runDoctor(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, "core", "services", "doctor.py")

	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		fmt.Printf("❌ Erro: Script do Doctor não encontrado em: %s\n", scriptPath)
		os.Exit(1)
	}

	pythonBin := getPythonBinary()

	// FIX: Integração completa de contexto (DRY)
	project := resolveProjectContext(args)
	projData, _ := core.GetProject(project)
	injectProjectEnv(project, projData)

	cmdArgs := []string{scriptPath}
	cmdArgs = append(cmdArgs, args...)

	c := exec.Command(pythonBin, cmdArgs...)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin

	c.Env = getPythonEnv(root)

	fmt.Println("🚑 Iniciando AI Doctor (Wrapper Go)...")
	if err := c.Run(); err != nil {
		if exitError, ok := err.(*exec.ExitError); ok {
			os.Exit(exitError.ExitCode())
		}
		fmt.Printf("❌ Erro na execução: %v\n", err)
		os.Exit(1)
	}
}
