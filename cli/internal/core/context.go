package core

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"aponte/cli/internal/utils"
)

// getContextFilePath retorna o caminho do arquivo de contexto isolado por usuário.
// Isso previne Race Conditions em ambientes compartilhados (Jump Hosts).
func getContextFilePath() string {
	root := utils.GetProjectRoot()
	user := utils.GetUser()

	session := os.Getenv("APONTE_SESSION_ID")
	if session == "" {
		session = "default"
	}
	// Organiza sessões em diretório oculto para não poluir a raiz
	return filepath.Join(root, ".aponte", "sessions", fmt.Sprintf("%s.%s", user, session))
}

// GetContext lê o projeto atual a partir do arquivo de estado oficial.
func GetContext() (string, error) {
	// 1. Prioridade Máxima: Variável de Ambiente (In-Memory)
	// Permite forçar um contexto (ex: "home") sem alterar o disco.
	if env := os.Getenv("TF_VAR_project_name"); env != "" {
		return strings.TrimSpace(env), nil
	}

	path := getContextFilePath()

	content, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return "home", nil
	}
	if err != nil {
		return "home", err
	}

	project := strings.TrimSpace(string(content))
	if project == "" {
		return "home", nil
	}
	return project, nil
}

// GetPersistedContext lê o contexto diretamente do disco, ignorando variáveis de ambiente.
// Útil para operações de limpeza (destroy/detach) que precisam saber o estado anterior.
func GetPersistedContext() (string, error) {
	content, err := os.ReadFile(getContextFilePath())
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(content)), nil
}

// SetContext define o projeto atual e atua como "zelador" do estado.
func SetContext(project string) error {
	path := getContextFilePath()

	// Garante que o diretório de sessões exista
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}

	if strings.TrimSpace(project) == "" {
		project = "home"
	}

	return os.WriteFile(path, []byte(strings.TrimSpace(project)), 0644)
}

// Wrappers para compatibilidade (se necessário, mas vamos refatorar direto)
func ResetContext() error { return SetContext("home") }
