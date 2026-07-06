#!/usr/bin/env python3
"""gates_detect.py - sniff a project and propose real mechanical gates.

CLI (not a hook): `python3 .claude/hooks/gates_detect.py [--write]`.

Detects the project stack (JS/TS, Python, Go, Rust, Makefile) and proposes
concrete gate commands ordered cheap-to-expensive (lint, typecheck, tests,
build). Only commands whose tool is actually invocable (shutil.which on the
binary) are proposed; the rest are reported as "detected_but_missing_tool" and
skipped on --write.

Without --write: prints a human table plus a machine-readable JSON line
(prefixed `GATES_JSON: `) and leaves company/gates.config untouched.

With --write: writes company/gates.config in the existing
`{"gates": [{"name", "command", "blocking": true}]}` shape, UNLESS the existing
config already holds a non-placeholder gate (a gate whose command contains
"CONFIGURE ME" is a placeholder and may be replaced). If no stack is detected
the config is left untouched either way.

Stdlib only. Exits 0 in the normal case.
"""

import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as c  # noqa: E402

# cheap-to-expensive ordering buckets
ORDER = {"lint": 0, "typecheck": 1, "tests": 2, "build": 3, "other": 4}

PLACEHOLDER_MARK = "configure me"


def project_dir():
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if root:
        return root
    return os.getcwd()


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def exists(root, name):
    return os.path.exists(os.path.join(root, name))


def gate(name, command, binary, kind):
    """Build a proposed-gate record."""
    return {
        "name": name,
        "command": command,
        "binary": binary,
        "kind": kind,
        "order": ORDER.get(kind, ORDER["other"]),
    }


def detect_node(root, gates, stacks):
    pkg_path = os.path.join(root, "package.json")
    if not os.path.exists(pkg_path):
        return None
    try:
        pkg = json.loads(read_text(pkg_path))
    except Exception:
        pkg = {}
    if not isinstance(pkg, dict):
        pkg = {}
    stacks.append("package.json")

    # package manager from lockfiles
    if exists(root, "pnpm-lock.yaml"):
        pm = "pnpm"
    elif exists(root, "yarn.lock"):
        pm = "yarn"
    else:
        pm = "npm"

    scripts = pkg.get("scripts") or {}
    if not isinstance(scripts, dict):
        scripts = {}

    def run_cmd(script):
        # `npm test` is idiomatic; other scripts go through `run`.
        if script == "test":
            return "{} test".format(pm)
        return "{} run {}".format(pm, script)

    if scripts.get("lint"):
        gates.append(gate("lint", run_cmd("lint"), pm, "lint"))
    if scripts.get("typecheck"):
        gates.append(gate("typecheck", run_cmd("typecheck"), pm, "typecheck"))
    else:
        deps = {}
        for key in ("dependencies", "devDependencies"):
            d = pkg.get(key)
            if isinstance(d, dict):
                deps.update(d)
        if "typescript" in deps:
            gates.append(
                gate("typecheck", "tsc --noEmit", "tsc", "typecheck")
            )
    if scripts.get("test"):
        gates.append(gate("tests", run_cmd("test"), pm, "tests"))
    if scripts.get("build"):
        gates.append(gate("build", run_cmd("build"), pm, "build"))
    return pm


def detect_python(root, gates, stacks):
    pyproject = os.path.join(root, "pyproject.toml")
    pyproject_txt = read_text(pyproject) if os.path.exists(pyproject) else ""
    setup_cfg_txt = (
        read_text(os.path.join(root, "setup.cfg"))
        if exists(root, "setup.cfg")
        else ""
    )
    tox_txt = (
        read_text(os.path.join(root, "tox.ini"))
        if exists(root, "tox.ini")
        else ""
    )

    test_signals = any(
        exists(root, f)
        for f in ("pyproject.toml", "setup.cfg", "pytest.ini", "conftest.py")
    )
    if not test_signals:
        return
    stacks.append("python")

    # lint: ruff, then flake8
    ruff_cfg = (
        "[tool.ruff" in pyproject_txt
        or exists(root, "ruff.toml")
        or exists(root, ".ruff.toml")
    )
    flake8_cfg = (
        exists(root, ".flake8")
        or "[flake8]" in setup_cfg_txt
        or "[flake8]" in tox_txt
    )
    if ruff_cfg:
        gates.append(gate("lint", "ruff check .", "ruff", "lint"))
    elif flake8_cfg:
        gates.append(gate("lint", "flake8", "flake8", "lint"))

    # typecheck: mypy
    mypy_cfg = (
        "[tool.mypy" in pyproject_txt
        or exists(root, "mypy.ini")
        or exists(root, ".mypy.ini")
        or "[mypy]" in setup_cfg_txt
    )
    if mypy_cfg:
        gates.append(gate("typecheck", "mypy .", "mypy", "typecheck"))

    # tests: pytest
    gates.append(gate("tests", "python3 -m pytest", "python3", "tests"))


def detect_go(root, gates, stacks):
    if not exists(root, "go.mod"):
        return
    stacks.append("go.mod")
    gates.append(gate("vet", "go vet ./...", "go", "lint"))
    gates.append(gate("tests", "go test ./...", "go", "tests"))


def detect_rust(root, gates, stacks):
    if not exists(root, "Cargo.toml"):
        return
    stacks.append("Cargo.toml")
    gates.append(
        gate("clippy", "cargo clippy -- -D warnings", "cargo", "lint")
    )
    gates.append(gate("tests", "cargo test", "cargo", "tests"))


def detect_make(root, gates, stacks):
    if not exists(root, "Makefile"):
        return
    txt = read_text(os.path.join(root, "Makefile"))
    targets = set()
    for line in txt.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+)\s*:", line)
        if m:
            targets.add(m.group(1))
    wanted = [("lint", "lint"), ("gates", "other"), ("test", "tests")]
    found = False
    for target, kind in wanted:
        if target in targets:
            found = True
            name = "tests" if target == "test" else target
            gates.append(
                gate(name, "make {}".format(target), "make", kind)
            )
    if found:
        stacks.append("Makefile")


def dedupe_and_order(gates):
    """Sort cheap-to-expensive, drop duplicate commands, unique-ify names."""
    ordered = sorted(
        enumerate(gates), key=lambda pair: (pair[1]["order"], pair[0])
    )
    seen_cmd = set()
    seen_name = {}
    out = []
    for _, g in ordered:
        cmd = g["command"]
        if cmd in seen_cmd:
            continue
        seen_cmd.add(cmd)
        name = g["name"]
        if name in seen_name:
            seen_name[name] += 1
            name = "{}-{}".format(name, seen_name[name])
        else:
            seen_name[name] = 1
        entry = dict(g)
        entry["name"] = name
        out.append(entry)
    return out


def split_invocable(gates):
    proposed, skipped = [], []
    for g in gates:
        if shutil.which(g["binary"]):
            proposed.append(g)
        else:
            skipped.append(g)
    return proposed, skipped


def config_has_real_gates(cfg):
    if not isinstance(cfg, dict):
        return False
    for g in cfg.get("gates") or []:
        if not isinstance(g, dict):
            continue
        cmd = str(g.get("command", ""))
        if cmd and PLACEHOLDER_MARK not in cmd.lower():
            return True
    return False


def to_config_gates(gates):
    return [
        {"name": g["name"], "command": g["command"], "blocking": True}
        for g in gates
    ]


def write_config(root, config_gates):
    path = os.path.join(root, "company", "gates.config")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = {
        "$comment": (
            "Auto-generated by gates_detect.py. Every gate is blocking; "
            "edit freely. See company/GATES.md."
        ),
        "gates": config_gates,
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(body, indent=2))
        f.write("\n")
    return path


def print_table(proposed, skipped, pm, stacks):
    if stacks:
        print("Detected stack: {}".format(", ".join(stacks)))
    if pm:
        print("Package manager: {}".format(pm))
    print("")
    header = "{:<12} {:<10} {}".format("GATE", "STATUS", "COMMAND")
    print(header)
    print("-" * len(header))
    for g in proposed:
        print("{:<12} {:<10} {}".format(g["name"], "ready", g["command"]))
    for g in skipped:
        print(
            "{:<12} {:<10} {}  (missing: {})".format(
                g["name"], "no-tool", g["command"], g["binary"]
            )
        )
    if not proposed and not skipped:
        print("(no gate candidates)")
    print("")


def emit_json(obj):
    print("GATES_JSON: " + json.dumps(obj, sort_keys=True))


def main(argv):
    write = "--write" in argv[1:]
    root = project_dir()

    gates = []
    stacks = []
    pm = detect_node(root, gates, stacks)
    detect_python(root, gates, stacks)
    detect_go(root, gates, stacks)
    detect_rust(root, gates, stacks)
    detect_make(root, gates, stacks)

    gates = dedupe_and_order(gates)
    proposed, skipped = split_invocable(gates)

    proposed_json = to_config_gates(proposed)
    skipped_json = [
        {
            "name": g["name"],
            "command": g["command"],
            "binary": g["binary"],
            "reason": "detected_but_missing_tool",
        }
        for g in skipped
    ]

    # No stack at all: leave config untouched, report, exit 0.
    if not stacks:
        print("no stack detected - leaving company/gates.config untouched")
        emit_json(
            {
                "stacks": [],
                "package_manager": pm,
                "proposed": [],
                "skipped": [],
                "wrote": False,
                "status": "no_stack",
            }
        )
        return 0

    print_table(proposed, skipped, pm, stacks)

    status = "proposed"
    wrote = False
    if write:
        existing = c.gates_config(root)
        if config_has_real_gates(existing):
            status = "preserved_existing"
            print(
                "company/gates.config already has real gates - preserved, "
                "not overwritten."
            )
        elif not proposed:
            status = "nothing_invocable"
            print(
                "no invocable gate commands on this machine - config left "
                "untouched."
            )
        else:
            path = write_config(root, proposed_json)
            wrote = True
            status = "wrote"
            print("wrote {} gate(s) to {}".format(len(proposed_json), path))

    emit_json(
        {
            "stacks": stacks,
            "package_manager": pm,
            "proposed": proposed_json,
            "skipped": skipped_json,
            "wrote": wrote,
            "status": status,
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
