package utils

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// ExecMCP executa um comando dentro do container MCP (mcp-terraform)
// garantindo paridade de runtime entre Dev e CI/CD (ADR-028).
func ExecMCP(dir string, binary string, args ...string) *exec.Cmd {
	root := GetProjectRoot()
	composeFile := filepath.Join(root, "config", "containers", "docker-compose.yml")

	// Monta o comando docker compose run
	dockerArgs := []string{
		"compose", "-f", composeFile, "run", "--rm",
		"-v", fmt.Sprintf("%s:/app", root),
	}

	// Define diretório de trabalho relativo a /app
	if dir != "" {
		// Se o caminho for absoluto, converte para relativo à raiz do projeto
		if filepath.IsAbs(dir) {
			if rel, err := filepath.Rel(root, dir); err == nil {
				dir = rel
			}
		}
		dockerArgs = append(dockerArgs, "-w", filepath.Join("/app", dir))
	} else {
		dockerArgs = append(dockerArgs, "-w", "/app")
	}

	// Forward de Variáveis de Ambiente Críticas
	// 1. Credenciais AWS & GitHub
	envVars := []string{
		"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
		"AWS_PROFILE", "AWS_REGION", "GITHUB_TOKEN",
		"TF_IN_AUTOMATION", "TERRAGRUNT_NON_INTERACTIVE",
	}
	for _, v := range envVars {
		if val := os.Getenv(v); val != "" {
			dockerArgs = append(dockerArgs, "-e", fmt.Sprintf("%s=%s", v, val))
		}
	}

	// FIX: Define variáveis de runtime essenciais para os scripts Python dentro do container
	// Isso garante que os hooks do Terragrunt encontrem os módulos 'core' e a raiz correta.
	// GIT_CONFIG_COUNT/KEY/VALUE corrige erro de "dubious ownership" de forma robusta.
	dockerArgs = append(dockerArgs,
		"-e", "PYTHONPATH=/app",
		"-e", "APONTE_ROOT=/app",
		"-e", "GIT_CONFIG_COUNT=1",
		"-e", "GIT_CONFIG_KEY_0=safe.directory",
		"-e", "GIT_CONFIG_VALUE_0=*",
	)

	// 2. Variáveis Terraform (TF_VAR_*) - Captura dinâmica
	for _, env := range os.Environ() {
		if strings.HasPrefix(env, "TF_VAR_") {
			dockerArgs = append(dockerArgs, "-e", env)
		}
	}

	dockerArgs = append(dockerArgs, "mcp-terraform", binary)
	dockerArgs = append(dockerArgs, args...)

	return exec.Command("docker", dockerArgs...)
}
