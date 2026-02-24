package validator

import (
	"fmt"
	"regexp"
	"strings"
)

func ValidateProjectName(name string) error {
	// 1. Validação de Vazio
	if len(strings.TrimSpace(name)) == 0 {
		return fmt.Errorf("o nome do projeto não pode ser vazio")
	}

	// 2. Validação de Tamanho (Max 30 chars)
	if len(name) > 30 {
		return fmt.Errorf("o nome do projeto é muito longo (máx 30 caracteres)")
	}

	// 3. Validação de Nomes Protegidos
	protected := map[string]bool{"home": true, "a-ponte": true, "root": true, "admin": true}
	if protected[name] {
		return fmt.Errorf("o nome '%s' é protegido e não pode ser usado", name)
	}

	// 4. Validação de Hífens nas pontas
	if strings.HasPrefix(name, "-") || strings.HasSuffix(name, "-") {
		return fmt.Errorf("o nome não pode começar ou terminar com hífen")
	}

	// 5. Validação de Caracteres (apenas minúsculas, números e hífens)
	matched, _ := regexp.MatchString(`^[a-z0-9-]+$`, name)
	if !matched {
		return fmt.Errorf("nome de projeto inválido: use apenas letras minúsculas, números e hífens")
	}
	return nil
}

func ValidateRepoName(name string) error {
	matched, _ := regexp.MatchString(`^[\w-]+/[\w.-]+$`, name)
	if !matched {
		return fmt.Errorf("nome de repositório inválido: formato esperado 'user/repo'")
	}
	return nil
}
