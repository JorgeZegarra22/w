"""CLI contract tests."""

from benter_peru.cli import build_parser


def test_cli_accepts_real_source_run_command() -> None:
    arguments = build_parser().parse_args(["run", "--source", "elinformativohipico"])

    assert arguments.command == "run"
    assert arguments.source == "elinformativohipico"


def test_cli_accepts_local_file() -> None:
    arguments = build_parser().parse_args(
        ["run", "--source", "elinformativohipico", "--local-file", "program.pdf"]
    )

    assert str(arguments.local_file) == "program.pdf"


def test_cli_accepts_entity_resolution_by_sha() -> None:
    sha256 = "a" * 64
    arguments = build_parser().parse_args(["resolve", "--sha", sha256])

    assert arguments.command == "resolve"
    assert arguments.sha == sha256
