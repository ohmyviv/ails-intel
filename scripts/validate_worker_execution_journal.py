from __future__ import annotations

import argparse

from ails_intel.worker_execution_journal import load_jsonl, validate_worker_execution_journal


def _required_routes(values: list[str]) -> dict[str, set[str]]:
    required: dict[str, set[str]] = {}
    for value in values:
        channel, sep, route_id = value.partition(":")
        if not sep or not channel.strip() or not route_id.strip():
            raise ValueError(f"invalid_required_route:{value}")
        required.setdefault(channel.strip(), set()).add(route_id.strip())
    return required


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a private Worker execution journal.")
    parser.add_argument("journal", help="Path to append-only JSONL execution journal")
    parser.add_argument(
        "--required-route",
        action="append",
        default=[],
        metavar="CHANNEL:ROUTE_ID",
        help="Expected route; repeat for each required route",
    )
    args = parser.parse_args()

    try:
        required = _required_routes(args.required_route)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    errors = validate_worker_execution_journal(
        load_jsonl(args.journal),
        required_routes=required or None,
    )
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print("worker_execution_journal=PASS")


if __name__ == "__main__":
    main()
