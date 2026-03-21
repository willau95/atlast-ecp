package ecp

import (
	"crypto/sha256"
	"fmt"
)

// HashContent computes SHA-256 hash of input string.
// Output format: "sha256:{hex}" — matches Python/TS SDK exactly.
func HashContent(input string) string {
	h := sha256.Sum256([]byte(input))
	return fmt.Sprintf("sha256:%x", h)
}
