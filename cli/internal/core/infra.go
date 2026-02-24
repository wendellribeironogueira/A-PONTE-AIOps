package core

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"aponte/cli/internal/docker"
	"aponte/cli/internal/utils"
)

// InfraManager handles local infrastructure orchestration via Docker Compose.
type InfraManager struct{}

// NewInfraManager creates a new instance of InfraManager.
func NewInfraManager() *InfraManager {
	return &InfraManager{}
}

// CheckDockerRunning verifies if the Docker daemon is accessible.
func (m *InfraManager) CheckDockerRunning(ctx context.Context) error {
	client, err := docker.NewClient()
	if err != nil {
		return fmt.Errorf("falha ao inicializar cliente Docker: %w", err)
	}
	if !client.IsRunning(ctx) {
		return fmt.Errorf("docker daemon não está rodando ou não está acessível")
	}
	return nil
}

// Up starts the infrastructure containers.
func (m *InfraManager) Up(profile string, args []string) error {
	fmt.Println("🚀 Inicializando infraestrutura local (A-PONTE)...")

	root := utils.GetProjectRoot()
	composeFile := filepath.Join(root, "config", "containers", "docker-compose.yml")

	dockerCmd := []string{"compose", "-f", composeFile}
	if profile != "" {
		dockerCmd = append(dockerCmd, "--profile", profile)
	}

	dockerArgs := append(dockerCmd, "up", "-d", "--remove-orphans")
	if len(args) > 0 {
		dockerArgs = append(dockerArgs, args...)
	}

	if err := m.runDocker(dockerArgs...); err != nil {
		return fmt.Errorf("falha ao subir infraestrutura: %w", err)
	}
	fmt.Println("✅ Infraestrutura online!")
	return nil
}

// Down stops the infrastructure containers.
func (m *InfraManager) Down() error {
	fmt.Println("🛑 Parando infraestrutura...")
	root := utils.GetProjectRoot()
	composeFile := filepath.Join(root, "config", "containers", "docker-compose.yml")

	if err := m.runDocker("compose", "-f", composeFile, "down", "--remove-orphans"); err != nil {
		return fmt.Errorf("falha ao parar infraestrutura: %w", err)
	}
	fmt.Println("✅ Infraestrutura parada.")
	return nil
}

// Reset resets the environment (Down + Up --force-recreate).
func (m *InfraManager) Reset(profile string, args []string) error {
	// Tenta parar (Best Effort)
	if err := m.Down(); err != nil {
		fmt.Printf("⚠️  Aviso: Erro ao parar containers (continuando reset): %v\n", err)
	}

	fmt.Println("🔄 Recriando containers (Force Recreate)...")
	root := utils.GetProjectRoot()
	composeFile := filepath.Join(root, "config", "containers", "docker-compose.yml")

	dockerCmd := []string{"compose", "-f", composeFile}
	if profile != "" {
		dockerCmd = append(dockerCmd, "--profile", profile)
	}

	dockerArgs := append(dockerCmd, "up", "-d", "--force-recreate", "--remove-orphans")
	if len(args) > 0 {
		dockerArgs = append(dockerArgs, args...)
	}

	if err := m.runDocker(dockerArgs...); err != nil {
		return fmt.Errorf("falha no reset: %w", err)
	}
	fmt.Println("✅ Ambiente resetado com sucesso.")
	return nil
}

// Build rebuilds the sandbox container.
func (m *InfraManager) Build() error {
	fmt.Println("🔨 Reconstruindo container mcp-terraform...")
	root := utils.GetProjectRoot()
	composeFile := filepath.Join(root, "config", "containers", "docker-compose.yml")

	if err := m.runDocker("compose", "-f", composeFile, "up", "-d", "--build", "mcp-terraform"); err != nil {
		return fmt.Errorf("falha no build: %w", err)
	}
	fmt.Println("✅ Build concluído.")
	return nil
}

// Prune cleans up unused Docker resources.
func (m *InfraManager) Prune() error {
	fmt.Println("🧹 Executando limpeza profunda do Docker (System Prune)...")
	fmt.Println("   Isso removerá containers parados, redes não usadas e imagens pendentes.")

	if err := m.runDocker("system", "prune", "-f"); err != nil {
		return fmt.Errorf("falha no prune: %w", err)
	}
	fmt.Println("✅ Limpeza concluída.")
	return nil
}

func (m *InfraManager) runDocker(args ...string) error {
	c := exec.Command("docker", args...)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	return c.Run()
}
