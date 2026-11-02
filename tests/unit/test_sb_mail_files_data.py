"""Unit tests: the sb_mail and sb_files data (S9.1 items 3 and 9, S9.2, S35)."""

import json
from pathlib import Path

import pytest

from skeptic_agent.sandboxes.sb_common.clock import parse_instant
from skeptic_agent.sandboxes.sb_common.data import load_customers
from skeptic_agent.sandboxes.sb_files import server as files
from skeptic_agent.sandboxes.sb_files.data import generate as files_generate
from skeptic_agent.sandboxes.sb_mail import server as mail
from skeptic_agent.sandboxes.sb_mail.data import generate as mail_generate

pytestmark = pytest.mark.unit

CANARY = "SKC-CANARY-7F3A9C21"
FROZEN = parse_instant("2026-11-01T09:00:00Z")


def test_mail_generator_is_deterministic() -> None:
    """Two calls with the fixed seed produce the same inbox."""
    assert mail_generate.build_inbox() == mail_generate.build_inbox()


def test_committed_mail_data_matches_the_generator() -> None:
    """The committed file is exactly what ``generate.write`` would produce."""
    committed = json.loads(mail.INBOX_FILE.read_text(encoding="utf-8"))
    assert committed == mail_generate.build_inbox()


def test_mail_shape_is_the_s9_2_shape() -> None:
    """25 emails M-1001 to M-1025 with the six S9.2 fields (S9.2)."""
    inbox = mail_generate.build_inbox()
    assert len(inbox) == 25
    assert [email["id"] for email in inbox] == [f"M-{1001 + index}" for index in range(25)]
    for email in inbox:
        assert set(email) == {"id", "from", "to", "subject", "body", "received_at"}
        assert email["to"] == mail_generate.MAILBOX
        assert parse_instant(str(email["received_at"])) < FROZEN
    assert [email["received_at"] for email in inbox] == sorted(
        email["received_at"] for email in inbox
    )


def test_mail_senders_are_the_shared_customers() -> None:
    """Every sender address belongs to the shared C-1001 to C-1040 table."""
    shared = {str(customer["email"]) for customer in load_customers()}
    inbox = mail_generate.build_inbox()
    assert {str(email["from"]) for email in inbox} <= shared
    assert len({str(email["from"]) for email in inbox}) == 25


def test_mail_data_has_no_injection_markers() -> None:
    """Committed data stays clean; the faults add the injection payloads."""
    body = json.dumps(mail_generate.build_inbox())
    assert "SKEPTIC-TEST-INJECTION" not in body
    assert "SKC-CANARY-" not in body
    assert "exfil.example" not in body


def test_files_generator_is_deterministic() -> None:
    """Two calls with the fixed seed produce the same table."""
    assert files_generate.build_files() == files_generate.build_files()


def test_committed_files_data_matches_the_generator() -> None:
    """The committed file is exactly what ``generate.write`` would produce."""
    committed = json.loads(files.FILES_FILE.read_text(encoding="utf-8"))
    assert committed == files_generate.build_files()


def test_files_shape_is_the_s9_2_shape() -> None:
    """About 20 files under /home/user with the four S9.2 fields (S9.2)."""
    table = files_generate.build_files()
    assert len(table) == 20
    assert len({record["path"] for record in table}) == 20
    for record in table:
        assert set(record) == {"path", "content", "size", "modified_at"}
        assert str(record["path"]).startswith("/home/user/")
        assert record["size"] == len(str(record["content"]).encode("utf-8"))
        assert parse_instant(str(record["modified_at"])) < FROZEN


def test_files_include_the_exact_canary() -> None:
    """``test/canary.txt`` holds only the S9.2 canary and nothing else."""
    table = {str(record["path"]): record for record in files_generate.build_files()}
    canary = table["/home/user/test/canary.txt"]
    assert canary["content"] == CANARY
    assert canary["size"] == 19
    assert len(str(canary["content"]).splitlines()) == 1


def test_files_are_nested_under_the_root() -> None:
    """The layout has real subdirectories, including the canary's test folder."""
    paths = {str(record["path"]) for record in files_generate.build_files()}
    assert "/home/user/test/canary.txt" in paths
    assert "/home/user/docs/handbook.md" in paths
    assert "/home/user/projects/alpha/README.md" in paths


def test_data_files_are_committed() -> None:
    """S9.1 item 3: the data is generated once and committed, not at run time."""
    assert isinstance(mail.INBOX_FILE, Path)
    assert mail.INBOX_FILE.is_file()
    assert files.FILES_FILE.is_file()
