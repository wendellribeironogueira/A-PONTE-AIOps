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

var scaffoldCmd = &cobra.Command{
	Use:   "scaffold",
	Short: "Gera estrutura de projeto via Cookiecutter",
	Long:  `Gera a estrutura inicial de um novo projeto (pastas, arquivos TF) usando templates Cookiecutter.`,
	Run:   runScaffoldCmd,
}

func init() {
	// Adiciona ao comando 'project' existente
	projectCmd.AddCommand(scaffoldCmd)
}

func runScaffoldCmd(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, "core", "tools", "scaffold.py")

	if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
		fmt.Printf("❌ Erro: Script de scaffold não encontrado em: %s\n", scriptPath)
		os.Exit(1)
	}

	pythonBin := getPythonBinary()

	// FIX: Injeta contexto se disponível (DRY/Integration)
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

	fmt.Println("🏗️  Iniciando Scaffold...")
	if err := c.Run(); err != nil {
		fmt.Printf("❌ Erro no scaffold: %v\n", err)
		os.Exit(1)
	}
}
