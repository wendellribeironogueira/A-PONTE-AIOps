package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"aponte/cli/internal/core"
	"aponte/cli/internal/docker"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var mcpCmd = &cobra.Command{
	Use:   "mcp",
	Short: "Gerencia o servidor MCP (Model Context Protocol)",
}

var mcpValidateCmd = &cobra.Command{
	Use:   "validate",
	Short: "Valida o ambiente e ferramentas do container MCP",
	Run:   runMcpValidate,
}

var mcpInspectCmd = &cobra.Command{
	Use:   "inspect",
	Short: "Lista as ferramentas disponíveis no container MCP",
	Run:   runMcpInspect,
}

func init() {
	rootCmd.AddCommand(mcpCmd)
	mcpCmd.AddCommand(mcpValidateCmd)
	mcpCmd.AddCommand(mcpInspectCmd)
}

func runMcpValidate(cmd *cobra.Command, args []string) {
	// Precondition: Verifica se o container está rodando
	client, err := docker.NewClient()
	if err == nil {
		containers, _ := client.ListContainers(cmd.Context())
		found := false
		for _, c := range containers {
			for _, name := range c.Names {
				if strings.Contains(name, "mcp-terraform") {
					found = true
					break
				}
			}
		}
		if !found {
			fmt.Println("❌ Erro: Container mcp-terraform não está rodando. Execute 'aponte infra up' primeiro.")
			os.Exit(1)
		}
	}

	runPythonTool("core/tools/mcp_validator.py")
}

func runMcpInspect(cmd *cobra.Command, args []string) {
	runPythonTool("core/tools/mcp_inspector.py")
}

func runPythonTool(relPath string) {
	root := utils.GetProjectRoot()
	scriptPath := filepath.Join(root, relPath)

	pythonBin := getPythonBinary()

	// FIX: Injeta contexto se disponível (DRY/Integration)
	if project, err := core.GetContext(); err == nil && project != "" && project != "home" {
		projData, _ := core.GetProject(project)
		injectProjectEnv(project, projData)
	}

	c := exec.Command(pythonBin, scriptPath)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Env = getPythonEnv(root)

	if err := c.Run(); err != nil {
		os.Exit(1)
	}
}
