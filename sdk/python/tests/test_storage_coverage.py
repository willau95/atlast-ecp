"""Additional coverage tests for storage.py."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from atlast_ecp.storage import (
    load_records,
    load_record_by_id,
    load_local_summary,
    enqueue_for_upload,
    get_upload_queue,
    clear_upload_queue,
    count_records,
)


class TestLoadRecords:
    def test_load_with_specific_date(self, tmp_path):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        f = records_dir / "2026-03-22.jsonl"
        f.write_text(json.dumps({"id": "rec_a", "agent": "a1"}) + "\n")

        with patch("atlast_ecp.storage.RECORDS_DIR", records_dir), \
             patch("atlast_ecp.storage.init_storage"):
            result = load_records(date="2026-03-22")
        assert len(result) == 1
        assert result[0]["id"] == "rec_a"

    def test_load_with_nonexistent_date(self, tmp_path):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        with patch("atlast_ecp.storage.RECORDS_DIR", records_dir), \
             patch("atlast_ecp.storage.init_storage"):
            result = load_records(date="2099-01-01")
        assert result == []

    def test_load_with_agent_filter(self, tmp_path):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        f = records_dir / "2026-03-22.jsonl"
        f.write_text(
            json.dumps({"id": "r1", "agent": "a1"}) + "\n" +
            json.dumps({"id": "r2", "agent": "a2"}) + "\n"
        )
        with patch("atlast_ecp.storage.RECORDS_DIR", records_dir), \
             patch("atlast_ecp.storage.init_storage"):
            result = load_records(date="2026-03-22", agent_id="a2")
        assert len(result) == 1
        assert result[0]["agent"] == "a2"

    def test_load_skips_corrupt_lines(self, tmp_path):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        f = records_dir / "2026-03-22.jsonl"
        f.write_text('{"id":"good"}\nnot-json\n')
        with patch("atlast_ecp.storage.RECORDS_DIR", records_dir), \
             patch("atlast_ecp.storage.init_storage"):
            result = load_records(date="2026-03-22")
        assert len(result) == 1

    def test_load_respects_limit(self, tmp_path):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        f = records_dir / "2026-03-22.jsonl"
        lines = [json.dumps({"id": f"r{i}"}) for i in range(20)]
        f.write_text("\n".join(lines) + "\n")
        with patch("atlast_ecp.storage.RECORDS_DIR", records_dir), \
             patch("atlast_ecp.storage.init_storage"):
            result = load_records(date="2026-03-22", limit=5)
        assert len(result) == 5


class TestLoadRecordById:
    def test_not_in_index(self, tmp_path):
        index_file = tmp_path / "index.json"
        index_file.write_text("{}")
        with patch("atlast_ecp.storage.init_storage"), \
             patch("atlast_ecp.storage._load_index", return_value={}):
            result = load_record_by_id("rec_nonexistent")
        assert result is None

    def test_file_missing(self, tmp_path):
        with patch("atlast_ecp.storage.init_storage"), \
             patch("atlast_ecp.storage._load_index", return_value={
                 "rec_x": {"file": str(tmp_path / "gone.jsonl")}
             }):
            result = load_record_by_id("rec_x")
        assert result is None

    def test_found_in_file(self, tmp_path):
        f = tmp_path / "data.jsonl"
        f.write_text(json.dumps({"id": "rec_found", "data": "yes"}) + "\n")
        with patch("atlast_ecp.storage.init_storage"), \
             patch("atlast_ecp.storage._load_index", return_value={
                 "rec_found": {"file": str(f)}
             }):
            result = load_record_by_id("rec_found")
        assert result is not None
        assert result["data"] == "yes"


class TestLocalSummary:
    def test_summary_exists(self, tmp_path):
        local_dir = tmp_path / "local"
        local_dir.mkdir()
        (local_dir / "rec_abc.txt").write_text("my summary")
        with patch("atlast_ecp.storage.LOCAL_DIR", local_dir):
            assert load_local_summary("rec_abc") == "my summary"

    def test_summary_not_exists(self, tmp_path):
        with patch("atlast_ecp.storage.LOCAL_DIR", tmp_path):
            assert load_local_summary("rec_none") is None


class TestUploadQueue:
    def test_enqueue_and_get(self, tmp_path):
        queue_file = tmp_path / "queue.jsonl"
        with patch("atlast_ecp.storage.QUEUE_FILE", queue_file), \
             patch("atlast_ecp.storage.init_storage"):
            enqueue_for_upload({"merkle_root": "sha256:abc"})
            enqueue_for_upload({"merkle_root": "sha256:def"})
        
        with patch("atlast_ecp.storage.QUEUE_FILE", queue_file):
            q = get_upload_queue()
        assert len(q) == 2

    def test_clear_queue(self, tmp_path):
        queue_file = tmp_path / "queue.jsonl"
        queue_file.write_text('{"x":1}\n')
        with patch("atlast_ecp.storage.QUEUE_FILE", queue_file):
            clear_upload_queue()
        assert queue_file.read_text() == ""

    def test_get_empty_queue(self, tmp_path):
        with patch("atlast_ecp.storage.QUEUE_FILE", tmp_path / "nope.jsonl"):
            assert get_upload_queue() == []


class TestCountRecords:
    def test_count_all(self, tmp_path):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        (records_dir / "a.jsonl").write_text('{"id":"1"}\n{"id":"2"}\n')
        (records_dir / "b.jsonl").write_text('{"id":"3"}\n')
        with patch("atlast_ecp.storage.RECORDS_DIR", records_dir), \
             patch("atlast_ecp.storage.init_storage"):
            assert count_records() == 3

    def test_count_by_date(self, tmp_path):
        records_dir = tmp_path / "records"
        records_dir.mkdir()
        (records_dir / "2026-03-22.jsonl").write_text('{"id":"1"}\n{"id":"2"}\n')
        with patch("atlast_ecp.storage.RECORDS_DIR", records_dir), \
             patch("atlast_ecp.storage.init_storage"):
            assert count_records(date="2026-03-22") == 2
