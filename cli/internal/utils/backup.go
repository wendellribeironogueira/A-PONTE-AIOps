package utils

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// VersionFile cria uma cópia de segurança versionada do arquivo alvo no diretório .aponte-versions.
// Retorna o caminho do backup criado ou erro.
// Se o arquivo não existir, retorna string vazia e nil (sem erro), permitindo fluxo contínuo.
func VersionFile(filePath string, projectName string, reason string) (string, error) {
	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		return "", nil
	}

	root := GetProjectRoot()

	// Sanitiza a razão para usar no path
	safeReason := strings.ReplaceAll(reason, " ", "_")
	// Aumenta precisão para milissegundos para evitar colisão em operações rápidas/concorrentes
	timestamp := time.Now().Format("20060102-150405.000")
	user := GetUser()

	// Estrutura: .aponte-versions/files/<project>/<timestamp>_<user>_<reason>/<filename>
	backupDir := filepath.Join(root, ".aponte-versions", "files", projectName, fmt.Sprintf("%s_%s_%s", timestamp, user, safeReason))

	// Tenta preservar a estrutura de diretórios relativa ao projeto
	var relPath string
	var baseDir string
	if projectName == "a-ponte" {
		baseDir = filepath.Join(root, "infrastructure", "bootstrap")
	} else {
		// Use 'projects' folder as base to capture config files (.yml, .repos)
		// that sit outside the project folder, preserving the hierarchy.
		baseDir = filepath.Join(root, "projects")
	}

	if rel, err := filepath.Rel(baseDir, filePath); err == nil && !strings.HasPrefix(rel, "..") {
		relPath = rel
	} else {
		// Fallback para arquivos fora da árvore padrão do projeto
		relPath = filepath.Base(filePath)
	}

	backupPath := filepath.Join(backupDir, relPath)

	// Garante que o diretório pai do arquivo de destino exista
	if err := os.MkdirAll(filepath.Dir(backupPath), 0755); err != nil {
		return "", fmt.Errorf("falha ao criar diretório de versão: %w", err)
	}

	// Usa a implementação robusta de cópia (com Sync e preservação de permissões)
	if err := CopyFile(filePath, backupPath); err != nil {
		return "", fmt.Errorf("falha na cópia segura: %w", err)
	}

	return backupPath, nil
}
