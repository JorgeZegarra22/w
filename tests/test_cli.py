"""CLI contract tests."""

from benter_peru.cli import build_parser


def test_cli_accepts_real_source_run_command() -> None:
    arguments = build_parser().parse_args(["run", "--source", "elinformativohipico"])

    assert arguments.command == "run"
    assert arguments.source == "elinformativohipico"
