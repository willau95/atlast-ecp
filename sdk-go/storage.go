package ecp

import (
	"bufio"
	"encoding/json"
	"os"
)

// DefaultPath returns the default ECP records path.
func DefaultPath() string {
	home, _ := os.UserHomeDir()
	return home + "/.atlast/records.jsonl"
}

// SaveRecord appends a record to a JSONL file.
// Creates parent directories if needed.
func SaveRecord(path string, record Record) error {
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}
	defer f.Close()

	data, err := json.Marshal(record)
	if err != nil {
		return err
	}
	_, err = f.Write(append(data, '\n'))
	return err
}

// LoadRecords reads all records from a JSONL file.
func LoadRecords(path string) ([]Record, error) {
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	defer f.Close()

	var records []Record
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := scanner.Text()
		if line == "" {
			continue
		}
		var r Record
		if err := json.Unmarshal([]byte(line), &r); err != nil {
			continue // skip malformed lines (fail-open)
		}
		records = append(records, r)
	}
	return records, scanner.Err()
}
