package git

import (
	"fmt"
	"os"

	"github.com/go-git/go-git/v5"
)

// Clone baixa um repositório remoto para o diretório local usando implementação nativa.
// Substitui a dependência do binário 'git' do sistema.
func Clone(url, destination string) error {
	_, err := git.PlainClone(destination, false, &git.CloneOptions{
		URL:      url,
		Progress: os.Stdout, // Mantém o feedback visual no terminal
	})
	if err != nil {
		return fmt.Errorf("falha no go-git: %w", err)
	}
	return nil
}

// IsRepository verifica se o caminho fornecido é um repositório git válido.
func IsRepository(path string) bool {
	_, err := git.PlainOpen(path)
	return err == nil
}
