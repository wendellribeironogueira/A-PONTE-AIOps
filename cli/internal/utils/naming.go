package utils

import (
	"regexp"
	"strings"
)

// NormalizeProjectName padroniza o nome do projeto para ser seguro em S3 e URLs.
// Regras: Lowercase, substitui caracteres inválidos por hífens, remove duplicatas e hífens nas pontas.
// Substitui a antiga lógica 'sed'.
func NormalizeProjectName(input string) string {
	// Lowercase
	s := strings.ToLower(input)
	// Replace invalid chars with -
	reg := regexp.MustCompile("[^a-z0-9-]+")
	s = reg.ReplaceAllString(s, "-")
	// Remove duplicate dashes
	regDash := regexp.MustCompile("-+")
	s = regDash.ReplaceAllString(s, "-")
	// Trim dashes (Melhoria em relação ao sed original)
	return strings.Trim(s, "-")
}
