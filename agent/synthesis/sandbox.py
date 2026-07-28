import json
import os
import subprocess
import sys
import tempfile

from agent.util import safe_jsonify

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

HARNESS_TEMPLATE = '''
import json
import sys

from agent.github_client import GitHubClient

{code}

def _main():
    args = json.loads(sys.argv[1])
    client = GitHubClient()
    result = run(args, client)
    print(json.dumps({{"ok": True, "result": result, "api_calls": client.call_count}}))

if __name__ == "__main__":
    try:
        _main()
    except Exception as exc:  # noqa: BLE001 -- report every failure mode to the caller
        print(json.dumps({{"ok": False, "error": f"{{type(exc).__name__}}: {{exc}}"}}))
'''


def test_capability(code: str, test_args: dict, timeout: int = 25) -> tuple[bool, dict]:
    """Executes `code` (which must define def run(args, client)) in a
    subprocess against the real GitHub API. Returns (ok, payload) where
    payload is either {"result": ..., "api_calls": n} or {"error": ...}."""
    harness = HARNESS_TEMPLATE.format(code=code)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir=tempfile.gettempdir()
    ) as f:
        f.write(harness)
        script_path = f.name

    env = dict(os.environ)
    env["PYTHONPATH"] = PROJECT_ROOT + os.pathsep + env.get("PYTHONPATH", "")

    try:
        proc = subprocess.run(
            [sys.executable, script_path, json.dumps(safe_jsonify(test_args))],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, {"error": f"synthesized tool timed out after {timeout}s"}
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass

    if proc.returncode != 0 and not proc.stdout.strip():
        return False, {"error": f"process exited {proc.returncode}: {proc.stderr[-500:]}"}

    last_line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        payload = json.loads(last_line)
    except (ValueError, IndexError):
        return False, {"error": f"no valid JSON output. stderr: {proc.stderr[-500:]}"}

    if not payload.get("ok"):
        return False, {"error": payload.get("error", "unknown error")}
    return True, payload
