package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"
	"aponte/cli/internal/validator"

	"github.com/spf13/cobra"
)

var utilsCmd = &cobra.Command{
	Use:    "utils",
	Short:  "Ferramentas utilitárias para scripts internos",
	Hidden: true,
}

var utilsNormalizeCmd = &cobra.Command{
	Use:   "normalize [string]",
	Short: "Normaliza uma string para formato de projeto (slug)",
	Args:  cobra.ExactArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Print(utils.NormalizeProjectName(args[0]))
	},
}

var utilsValidateProjectCmd = &cobra.Command{
	Use:   "validate-project [name]",
	Short: "Valida se um nome de projeto é válido",
	Args:  cobra.ExactArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		if err := validator.ValidateProjectName(args[0]); err != nil {
			fmt.Print(err.Error())
			os.Exit(1)
		}
	},
}

func init() {
	rootCmd.AddCommand(utilsCmd)
	utilsCmd.AddCommand(utilsNormalizeCmd)
	utilsCmd.AddCommand(utilsValidateProjectCmd)
}

// injectProjectEnv configura as variáveis de ambiente padrão para Terraform e Scripts Python
// baseadas nos metadados do projeto.
func injectProjectEnv(project string, projData *core.Project) {
	os.Setenv("TF_VAR_project_name", project)
	if projData != nil {
		os.Setenv("TF_VAR_environment", projData.Environment)
		os.Setenv("TF_VAR_security_email", projData.SecurityEmail)

		if len(projData.Repositories) > 0 {
			reposJson, _ := json.Marshal(projData.Repositories)
			os.Setenv("TF_VAR_github_repos", string(reposJson))
		}
	}
}

// getEncodedProjectEnv retorna variáveis de ambiente formatadas para o comando 'env' (KEY=VAL)
// Filtra apenas TF_VAR_ para passar para o container Docker via ExecMCP
func getEncodedProjectEnv() []string {
	prefixes := []string{"TF_VAR_", "ALLOW_APONTE_MODIFICATIONS", "GITHUB_", "GH_", "INFRACOST_", "APONTE_"}
	var vars []string
	for _, e := range os.Environ() {
		for _, p := range prefixes {
			if strings.HasPrefix(e, p) {
				vars = append(vars, e)
				break
			}
		}
	}
	return vars
}

// execMCPWithProjectEnv executa um comando no container MCP injetando automaticamente as variáveis do projeto
func execMCPWithProjectEnv(dir string, command ...string) *exec.Cmd {
	cmdArgs := []string{"env"}
	cmdArgs = append(cmdArgs, getEncodedProjectEnv()...)
	cmdArgs = append(cmdArgs, command...)
	return utils.ExecMCP(dir, cmdArgs[0], cmdArgs[1:]...)
}

// execPythonInMCP executa um script Python dentro do container MCP com ambiente configurado
func execPythonInMCP(script string, args ...string) *exec.Cmd {
	cmdArgs := []string{"env", "PYTHONPATH=/app", "OLLAMA_URL=http://host.docker.internal:11434/api/generate"}
	cmdArgs = append(cmdArgs, getEncodedProjectEnv()...)
	cmdArgs = append(cmdArgs, "python3", script)
	cmdArgs = append(cmdArgs, args...)
	return utils.ExecMCP(utils.GetProjectRoot(), cmdArgs[0], cmdArgs[1:]...)
}

// getPythonEnv retorna as variáveis de ambiente padrão para execução de scripts Python (APONTE_ROOT, PYTHONPATH)
func getPythonEnv(root string) []string {
	env := os.Environ()
	env = append(env, fmt.Sprintf("APONTE_ROOT=%s", root))
	env = append(env, fmt.Sprintf("PYTHONPATH=%s", root))
	return env
}

// getPythonBinary retorna o caminho do interpretador Python, priorizando o VIRTUAL_ENV
func getPythonBinary() string {
	if venv := os.Getenv("VIRTUAL_ENV"); venv != "" {
		if runtime.GOOS == "windows" {
			return filepath.Join(venv, "Scripts", "python.exe")
		}
		return filepath.Join(venv, "bin", "python")
	}
	// Fallback para o sistema
	if runtime.GOOS == "windows" {
		return "python"
	}
	return "python3"
}
