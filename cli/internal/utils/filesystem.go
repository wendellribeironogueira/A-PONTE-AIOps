package utils

import (
	"fmt"
	"io"
	"os"
)

// CopyFile copia um arquivo da origem para o destino de forma robusta.
// Garante:
// 1. Flush no disco (Sync) para evitar corrupção em caso de falha de energia.
// 2. Preservação de permissões (chmod) do arquivo original.
func CopyFile(src, dst string) error {
	sourceFileStat, err := os.Stat(src)
	if err != nil {
		return fmt.Errorf("erro ao ler status da origem: %w", err)
	}

	if !sourceFileStat.Mode().IsRegular() {
		return fmt.Errorf("%s não é um arquivo regular", src)
	}

	sourceFile, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("erro ao abrir origem: %w", err)
	}
	defer sourceFile.Close()

	destFile, err := os.Create(dst)
	if err != nil {
		return fmt.Errorf("erro ao criar destino: %w", err)
	}
	defer destFile.Close()

	if _, err := io.Copy(destFile, sourceFile); err != nil {
		return fmt.Errorf("erro ao copiar dados: %w", err)
	}

	// Garante integridade física dos dados
	if err := destFile.Sync(); err != nil {
		return fmt.Errorf("erro ao fazer flush no disco: %w", err)
	}

	// Preserva permissões (ex: executável)
	return os.Chmod(dst, sourceFileStat.Mode())
}
