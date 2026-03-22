# ATLAST ECP — Go SDK

> Evidence Chain Protocol SDK for Go. Create, store, and verify ECP records.

## Install

```bash
go get github.com/willau95/atlast-ecp/sdk/go
```

## Quick Start

```go
package main

import (
    "fmt"
    ecp "github.com/willau95/atlast-ecp/sdk-go"
)

func main() {
    // Create a minimal ECP record (Level 1 — 7 fields)
    record := ecp.NewMinimalRecord("my-agent", "llm_call", "user query", "agent response")
    
    // Save to local JSONL file
    ecp.SaveRecord(ecp.DefaultPath(), record)
    
    // Verify hash
    fmt.Println(record.InHash)   // sha256:...
    fmt.Println(record.OutHash)  // sha256:...
}
```

## CLI

```bash
go install github.com/willau95/atlast-ecp/sdk-go/cmd/atlast@latest

# Record an action
atlast record --agent my-agent --input "hello" --output "world"

# View records
atlast log

# Verify integrity
atlast verify --json
```

## API Reference

| Function | Description |
|----------|-------------|
| `NewMinimalRecord(agent, action, input, output)` | Create Level 1 record (7 fields) |
| `NewRecord(agent, action, input, output, meta)` | Create Level 2 record with metadata |
| `HashContent(input)` | SHA-256 hash (`sha256:{hex}`) |
| `SaveRecord(path, record)` | Append record to JSONL file |
| `LoadRecords(path)` | Load all records from JSONL file |
| `BuildMerkleRoot(hashes)` | Compute Merkle root from hash list |
| `VerifyMerkleRoot(hashes, root)` | Verify Merkle root matches hashes |
| `ComputeChainHash(record)` | Compute chain hash for a record |
| `VerifyChain(records)` | Verify record chain integrity |

## Cross-SDK Compatibility

Go SDK produces records that are **fully interoperable** with Python and TypeScript SDKs:

- Same hash output: `HashContent("hello")` matches across all SDKs
- Same record ID format: `rec_` + 16 hex characters
- Same JSONL storage format: records created in Go can be read by Python and vice versa
- Same Merkle root algorithm: sort → pair → SHA-256

## Zero Dependencies

This SDK uses only Go standard library (`crypto/sha256`, `encoding/json`, `os`). No external dependencies.

## License

MIT
