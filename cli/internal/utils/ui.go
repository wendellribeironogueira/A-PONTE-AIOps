package utils

import (
	"bufio"
	"fmt"
	"os"
	"strings"
)

// ConfirmAction solicita confirmação do usuário (Suporta PT/EN)
func ConfirmAction(prompt string, expected ...string) bool {
	if os.Getenv("FORCE_NON_INTERACTIVE") == "true" {
		return true
	}
	fmt.Printf("%s ", prompt)
	reader := bufio.NewReader(os.Stdin)
	resp, _ := reader.ReadString('\n')
	resp = strings.TrimSpace(resp)

	if len(expected) > 0 {
		return resp == expected[0]
	}

	val := strings.ToLower(resp)
	return val == "y" || val == "yes" || val == "s" || val == "sim"
}

// Prompt solicita entrada de texto do usuário
func Prompt(label string) string {
	fmt.Printf("%s ", label)
	reader := bufio.NewReader(os.Stdin)
	resp, _ := reader.ReadString('\n')
	return strings.TrimSpace(resp)
}
