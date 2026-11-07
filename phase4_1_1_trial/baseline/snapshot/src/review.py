"""Explicit isolated migration/review CLI. No fetch or external delivery."""
import argparse
import json
from src import state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--migrate", action="store_true")
    group.add_argument("--list-pending", action="store_true")
    group.add_argument("--event-id")
    parser.add_argument("--decision", choices=("CONFIRM", "REJECT", "KEEP"))
    parser.add_argument("--reason")
    args = parser.parse_args()
    try:
        path = state._isolated_path(args.state)
        if args.migrate:
            result = state.migrate_path(path)
        elif args.list_pending:
            value = state.load(path)
            result = [e for e in value.get("event_records", {}).values() if e.get("status") == "PENDING_REVIEW"]
        else:
            if not args.decision or not args.reason:
                parser.error("An explicit decision and rationale are required")
            result = state.review_event(path, args.event_id, args.decision, args.reason)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
