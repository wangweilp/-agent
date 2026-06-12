"""CLI for Cognitive Agent Manifest SDK.

Usage:
    python -m cognitive_agent_sdk.cli validate path/to/manifest.json
    python -m cognitive_agent_sdk.cli validate path/to/manifest.json --strict
    python -m cognitive_agent_sdk.cli example minimal
    python -m cognitive_agent_sdk.cli example package-metadata
    python -m cognitive_agent_sdk.cli example invalid-network
    python -m cognitive_agent_sdk.cli schema

Exit codes: 0=valid, 1=invalid (errors/blockers), 2=file/usage error
No network calls. No code execution. No package download.
"""

import json
import sys

from cognitive_agent_sdk.validator import validate_manifest_dict, load_manifest_file
from cognitive_agent_sdk import examples


def cmd_validate(path: str, strict: bool = True) -> int:
    try:
        data = load_manifest_file(path)
        result = validate_manifest_dict(data, strict)
    except FileNotFoundError:
        print(json.dumps({"error": f"File not found: {path}", "exit_code": 2}))
        return 2
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}", "exit_code": 2}))
        return 2

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    if not result.valid:
        return 1
    if result.has_warnings:
        ## warnings don't fail exit code
        return 0
    return 0


def cmd_example(name: str) -> int:
    builders = {
        "minimal": examples.build_minimal_manifest,
        "package-metadata": examples.build_package_metadata_manifest,
        "invalid-network": examples.build_invalid_network_manifest,
    }
    builder = builders.get(name)
    if builder is None:
        print(json.dumps({"error": f"Unknown example: {name}. Available: {list(builders.keys())}", "exit_code": 2}))
        return 2
    data = builder()
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def cmd_schema() -> int:
    print("Loading schema from schemas/cognitive-agent.schema.json is not supported via CLI.")
    print("Use GET /developers/agent-manifest/schema API endpoint or read the file directly.")
    return 2


def main() -> None:
    args = sys.argv[1:] if len(sys.argv) > 1 else ["--help"]
    if not args or args[0] in ("-h", "--help"):
        print("Cognitive Agent SDK — Manifest validator")
        print("  python -m cognitive_agent_sdk.cli validate <file> [--no-strict]")
        print("  python -m cognitive_agent_sdk.cli example <name>")
        print("  python -m cognitive_agent_sdk.cli schema")
        sys.exit(0)

    cmd = args[0]
    strict = "--no-strict" not in args
    remaining = [a for a in args[1:] if not a.startswith("--")]

    if cmd == "validate":
        if not remaining:
            print(json.dumps({"error": "Usage: validate <file>", "exit_code": 2}))
            sys.exit(2)
        sys.exit(cmd_validate(remaining[0], strict))
    elif cmd == "example":
        name = remaining[0] if remaining else "minimal"
        sys.exit(cmd_example(name))
    elif cmd == "schema":
        sys.exit(cmd_schema())
    else:
        print(json.dumps({"error": f"Unknown command: {cmd}", "exit_code": 2}))
        sys.exit(2)


if __name__ == "__main__":
    main()
