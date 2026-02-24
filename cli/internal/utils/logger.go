package utils

import "log"

// Logger provides logging utilities for the CLI.
// Currently using standard log package.
func Log(msg string) {
	log.Println(msg)
}
