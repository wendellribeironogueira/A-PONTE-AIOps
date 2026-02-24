package utils

import "testing"

func TestNormalizeProjectName(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{"Simples", "MyProject", "myproject"},
		{"Com Espaços", "My Project", "my-project"},
		{"Caracteres Especiais", "Project@123!", "project-123-"},
		{"Hífens Repetidos", "a--b", "a-b"},
		{"Hífens nas Pontas", "-project-", "project"}, // Melhoria sobre o sed original
		{"Misturado", "  My_Cool--Project  ", "my-cool-project"},
		{"Vazio", "", ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := NormalizeProjectName(tt.input)
			if got != tt.expected {
				t.Errorf("NormalizeProjectName(%q) = %q; want %q", tt.input, got, tt.expected)
			}
		})
	}
}
