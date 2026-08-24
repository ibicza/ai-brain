def main() -> int:
    """Load the development CLI lazily so trusted subpackages stay CPU-only."""
    from ai_brain.cli import main as cli_main

    return cli_main()


__all__ = ["main"]
