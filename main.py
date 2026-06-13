from demo.cli_demo import DEFAULT_INPUT, DEFAULT_MEMORY_PATH, run_demo


def main(run_cli_demo: bool = False) -> int:
    """Run the deterministic CLI demo when invoked as a script."""
    if run_cli_demo:
        print(run_demo(DEFAULT_INPUT, DEFAULT_MEMORY_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(run_cli_demo=True))
