"""Diagnose /openapi.json ForwardRef failure.  Don't fix — only locate."""

import io
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main():
    # Silence noisy startup logs
    import logging
    logging.getLogger().setLevel(logging.WARNING)
    for name in logging.root.manager.loggerDict:
        logging.getLogger(name).setLevel(logging.WARNING)

    print("Loading app…")
    from main import app
    print(f"App loaded.  Routes: {len(app.routes)}\n")

    print("Calling app.openapi()…")
    try:
        schema = app.openapi()
        print(f"OK: paths={len(schema.get('paths', {}))}")
    except Exception:
        tb = traceback.format_exc()
        print(tb)

        # ── Parse the traceback for ForwardRef clues ──
        print("\n" + "=" * 70)
        print("ANALYSIS")
        print("=" * 70)

        # Grab the last few frames
        frames = traceback.extract_tb(sys.exc_info()[2])
        for f in frames:
            if "site-packages" not in f.filename:
                print(f"  PROJECT: {f.filename}:{f.lineno} in {f.name}")

        # Regex scan for ForwardRef name
        import re
        match = re.search(r"ForwardRef\('([^']+)'\)", tb)
        if match:
            print(f"\n  ForwardRef target: '{match.group(1)}'")

        match2 = re.search(r"ForwardRef\(['\"]([^'\"]+)['\"]\)", tb)
        if match2:
            print(f"  ForwardRef target (alt): '{match2.group(1)}'")

        # Also scan for 'WorkerPreviewReq' if present
        if "WorkerPreviewReq" in tb:
            print("\n  Confirmed: 'WorkerPreviewReq' referenced in traceback")
            # Find where WorkerPreviewReq is defined
            for root, dirs, files in os.walk("src"):
                for fn in files:
                    if fn.endswith(".py"):
                        path = os.path.join(root, fn)
                        try:
                            with open(path, encoding="utf-8") as fh:
                                for i, line in enumerate(fh, 1):
                                    if "WorkerPreviewReq" in line:
                                        print(f"    Defined/used: {path}:{i}: {line.rstrip()}")
                        except Exception:
                            pass

        # Try to locate the annotating model
        print("\n" + "=" * 70)
        print("SEARCHING FOR ForwardRef USAGE")
        print("=" * 70)
        for root, dirs, files in os.walk("src"):
            for fn in files:
                if fn.endswith(".py"):
                    path = os.path.join(root, fn)
                    try:
                        with open(path, encoding="utf-8") as fh:
                            for i, line in enumerate(fh, 1):
                                if "ForwardRef" in line:
                                    print(f"  {path}:{i}: {line.rstrip()}")
                    except Exception:
                        pass


if __name__ == "__main__":
    main()
