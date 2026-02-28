from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
import shlex
import subprocess
import time

@dataclass(slots=True)
class VerificationStepResult:
    name: str
    command: str
    exit_code: int
    status: str
    duration_ms: int
    stdout: str = ""
    stderr: str = ""

@dataclass(slots=True)
class VerificationReport:
    repo: str
    rounds: int
    passed: bool
    static_passed: bool
    tests_passed: bool
    auto_repairs_attempted: int
    steps: list[VerificationStepResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "repo": self.repo,
            "rounds": self.rounds,
            "passed": self.passed,
            "static_passed": self.static_passed,
            "tests_passed": self.tests_passed,
            "auto_repairs_attempted": self.auto_repairs_attempted,
            "steps": [
                {
                    "name": step.name,
                    "command": step.command,
                    "exit_code": step.exit_code,
                    "status": step.status,
                    "duration_ms": step.duration_ms,
                    "stdout": step.stdout,
                    "stderr": step.stderr,
                }
                for step in self.steps
            ],
        }


class VerificationAgent:
    def __init__(self, repo_root: Path, python_executable: str = "python") -> None:
        self.repo_root = repo_root
        self.python_executable = python_executable

    def run(self, max_rounds: int = 2, auto_repair: bool = True) -> VerificationReport:
        rounds = 0
        repairs = 0
        all_steps: list[VerificationStepResult] = []
        static_passed = False
        tests_passed = False

        while rounds < max_rounds:
            rounds += 1
            static_steps, static_passed = self._run_static_checks()
            test_steps, tests_passed = self._run_tests()
            all_steps.extend(static_steps)
            all_steps.extend(test_steps)

            if static_passed and tests_passed:
                break

            if not auto_repair or rounds >= max_rounds:
                break

            did_repair, repair_steps = self._attempt_safe_repairs(static_steps, test_steps)
            all_steps.extend(repair_steps)
            if not did_repair:
                break
            repairs += 1

        return VerificationReport(
            repo=str(self.repo_root),
            rounds=rounds,
            passed=static_passed and tests_passed,
            static_passed=static_passed,
            tests_passed=tests_passed,
            auto_repairs_attempted=repairs,
            steps=all_steps,
        )

    def _run_static_checks(self) -> tuple[list[VerificationStepResult], bool]:
        syntax_step = _run_syntax_check(self.repo_root)
        commands = [("ruff", [self.python_executable, "-m", "ruff", "check", "."])]

        steps: list[VerificationStepResult] = [syntax_step]
        ok = syntax_step.exit_code == 0
        for name, command in commands:
            result = _run_command(name, command, self.repo_root)
            if _is_missing_python_module(result):
                result.status = "missing"
            if result.status == "missing":
                continue
            steps.append(result)
            ok = ok and result.exit_code == 0

        build_steps, build_ok = self._run_build_system_checks()
        steps.extend(build_steps)
        ok = ok and build_ok
        return steps, ok

    def _run_build_system_checks(self) -> tuple[list[VerificationStepResult], bool]:
        steps: list[VerificationStepResult] = []
        ok = True

        has_cmake = any(self.repo_root.rglob("CMakeLists.txt"))
        has_gradle = any(self.repo_root.rglob("build.gradle")) or any(self.repo_root.rglob("build.gradle.kts"))
        has_package_json = any(self.repo_root.rglob("package.json"))
        has_maven = any(self.repo_root.rglob("pom.xml"))
        has_dotnet = any(self.repo_root.rglob("*.csproj"))

        if has_cmake:
            cmake_version = _run_command("cmake_version", ["cmake", "--version"], self.repo_root)
            if cmake_version.status == "missing":
                pass
            else:
                steps.append(cmake_version)
                ok = ok and cmake_version.exit_code == 0

        if has_gradle:
            gradle_version = _run_command("gradle_version", ["gradle", "--version"], self.repo_root)
            if gradle_version.status == "missing":
                pass
            else:
                steps.append(gradle_version)
                ok = ok and gradle_version.exit_code == 0

        if has_package_json:
            node_version = _run_command("node_version", ["node", "--version"], self.repo_root)
            if node_version.status != "missing":
                steps.append(node_version)
                ok = ok and node_version.exit_code == 0

            npm_version = _run_command("npm_version", ["npm", "--version"], self.repo_root)
            if npm_version.status != "missing":
                steps.append(npm_version)
                ok = ok and npm_version.exit_code == 0

        if has_maven:
            mvn_version = _run_command("maven_version", ["mvn", "-version"], self.repo_root)
            if mvn_version.status != "missing":
                steps.append(mvn_version)
                ok = ok and mvn_version.exit_code == 0

        if has_dotnet:
            dotnet_version = _run_command("dotnet_version", ["dotnet", "--version"], self.repo_root)
            if dotnet_version.status != "missing":
                steps.append(dotnet_version)
                ok = ok and dotnet_version.exit_code == 0

        return steps, ok

    def _run_tests(self) -> tuple[list[VerificationStepResult], bool]:
        test_roots = _discover_python_test_roots(self.repo_root)
        stack_candidates = _discover_stack_test_candidates(self.repo_root)

        if not test_roots and not stack_candidates:
            return [
                VerificationStepResult(
                    name="tests",
                    command="<none>",
                    exit_code=0,
                    status="skipped",
                    duration_ms=0,
                    stdout="No test roots detected for python/js/java/dotnet.",
                    stderr="",
                )
            ], True

        candidates: list[tuple[str, list[str], Path]] = []
        if test_roots:
            root_args = [path.as_posix() for path in test_roots]
            candidates.extend(
                [
                    (
                        "pytest",
                        [self.python_executable, "-m", "pytest", "-q", *root_args, "--ignore-glob", "src/**/test_*.py"],
                        self.repo_root,
                    ),
                    (
                        "unittest",
                        [self.python_executable, "-m", "unittest", "discover", "-s", root_args[0], "-p", "test*.py"],
                        self.repo_root,
                    ),
                ]
            )

        candidates.extend(stack_candidates)

        executed: list[VerificationStepResult] = []
        ok = True
        for name, command, cwd in candidates:
            result = _run_command(name, command, cwd)
            if _is_missing_python_module(result):
                result.status = "missing"
            if result.status == "missing":
                continue
            executed.append(result)
            ok = ok and result.exit_code == 0

        if executed:
            return executed, ok

        return [
            VerificationStepResult(
                name="tests",
                command="<none>",
                exit_code=0,
                status="skipped",
                duration_ms=0,
                stdout="No test runner available (pytest/unittest).",
                stderr="",
            )
        ], True

    def _attempt_safe_repairs(
        self,
        static_steps: list[VerificationStepResult],
        test_steps: list[VerificationStepResult],
    ) -> tuple[bool, list[VerificationStepResult]]:
        repair_steps: list[VerificationStepResult] = []
        attempted = False

        if any(step.name == "ruff" and step.exit_code != 0 for step in static_steps):
            fix_step = _run_command(
                "ruff_fix",
                [self.python_executable, "-m", "ruff", "check", ".", "--fix"],
                self.repo_root,
            )
            if _is_missing_python_module(fix_step):
                fix_step.status = "missing"
            if fix_step.status != "missing":
                repair_steps.append(fix_step)
                attempted = True

        syntax_step = next((step for step in static_steps if step.name == "syntax"), None)
        if syntax_step and syntax_step.exit_code != 0 and "U+FEFF" in syntax_step.stdout:
            bom_fix_step = _repair_utf8_bom_files(self.repo_root, syntax_step.stdout)
            repair_steps.append(bom_fix_step)
            attempted = attempted or bom_fix_step.exit_code == 0

        if not attempted and any(step.exit_code != 0 for step in test_steps if step.status == "ok"):
            note = VerificationStepResult(
                name="repair_hint",
                command="<manual>",
                exit_code=1,
                status="ok",
                duration_ms=0,
                stdout="Tests failed with no safe deterministic auto-fix available.",
                stderr="Inspect test output and apply targeted code changes.",
            )
            repair_steps.append(note)

        return attempted, repair_steps

def _run_command(name: str, command: list[str], cwd: Path) -> VerificationStepResult:
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        elapsed = int((time.perf_counter() - start) * 1000)
        return VerificationStepResult(
            name=name,
            command=shlex.join(command),
            exit_code=completed.returncode,
            status="ok",
            duration_ms=elapsed,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except FileNotFoundError:
        elapsed = int((time.perf_counter() - start) * 1000)
        return VerificationStepResult(
            name=name,
            command=shlex.join(command),
            exit_code=127,
            status="missing",
            duration_ms=elapsed,
            stdout="",
            stderr="Command not found",
        )

def _is_missing_python_module(result: VerificationStepResult) -> bool:
    if "No module named" in result.stderr:
        return True
    return False

def _run_syntax_check(repo_root: Path) -> VerificationStepResult:
    start = time.perf_counter()
    ignored_parts = {".venv", "venv", "__pycache__", ".git", ".dist"}
    errors: list[str] = []
    checked = 0

    for path in repo_root.rglob("*.py"):
        if any(part in ignored_parts for part in path.parts):
            continue
        checked += 1
        source = path.read_text(encoding="utf-8", errors="ignore")
        try:
            ast.parse(source)
        except SyntaxError as exc:
            relative = path.relative_to(repo_root).as_posix()
            errors.append(f"{relative}:{exc.lineno}:{exc.offset}: {exc.msg}")

    elapsed = int((time.perf_counter() - start) * 1000)
    if errors:
        return VerificationStepResult(
            name="syntax",
            command="internal:ast-parse",
            exit_code=1,
            status="ok",
            duration_ms=elapsed,
            stdout="\n".join(errors),
            stderr="",
        )

    return VerificationStepResult(
        name="syntax",
        command="internal:ast-parse",
        exit_code=0,
        status="ok",
        duration_ms=elapsed,
        stdout=f"Parsed {checked} Python file(s).",
        stderr="",
    )


def _discover_python_test_roots(repo_root: Path) -> list[Path]:
    ignored_parts = {".venv", "venv", "__pycache__", ".git", ".dist", "node_modules", "bin", "obj"}
    roots: set[Path] = set()
    for path in repo_root.rglob("*.py"):
        if any(part in ignored_parts for part in path.parts):
            continue
        parent_name = path.parent.name.lower()
        if parent_name in {"tests", "test"}:
            roots.add(path.parent)
    return sorted(roots)


def _discover_stack_test_candidates(repo_root: Path) -> list[tuple[str, list[str], Path]]:
    ignored_parts = {".venv", "venv", "__pycache__", ".git", ".dist", "node_modules", "bin", "obj"}
    candidates: list[tuple[str, list[str], Path]] = []

    # JavaScript / TypeScript
    for package_json in repo_root.rglob("package.json"):
        if any(part in ignored_parts for part in package_json.parts):
            continue
        package_dir = package_json.parent
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8", errors="ignore"))
        except json.JSONDecodeError:
            continue
        scripts = payload.get("scripts", {})
        if isinstance(scripts, dict) and isinstance(scripts.get("test"), str):
            relative = package_dir.relative_to(repo_root).as_posix() or "."
            candidates.append((f"npm_test:{relative}", ["npm", "test", "--silent"], package_dir))

    # Maven
    for pom in repo_root.rglob("pom.xml"):
        if any(part in ignored_parts for part in pom.parts):
            continue
        module_dir = pom.parent
        relative = module_dir.relative_to(repo_root).as_posix() or "."
        candidates.append((f"maven_test:{relative}", ["mvn", "-q", "test"], module_dir))

    # .NET
    sln_files = [path for path in repo_root.rglob("*.sln") if not any(part in ignored_parts for part in path.parts)]
    if sln_files:
        for sln in sln_files:
            relative = sln.relative_to(repo_root).as_posix()
            candidates.append((f"dotnet_test:{relative}", ["dotnet", "test", sln.as_posix(), "--nologo", "--verbosity", "minimal"], repo_root))
    else:
        for csproj in repo_root.rglob("*.csproj"):
            if any(part in ignored_parts for part in csproj.parts):
                continue
            lowered = csproj.stem.lower()
            if "test" not in lowered:
                continue
            relative = csproj.relative_to(repo_root).as_posix()
            candidates.append((f"dotnet_test:{relative}", ["dotnet", "test", csproj.as_posix(), "--nologo", "--verbosity", "minimal"], repo_root))

    deduped: list[tuple[str, list[str], Path]] = []
    seen: set[tuple[str, str]] = set()
    for name, command, cwd in candidates:
        key = (name, cwd.as_posix())
        if key in seen:
            continue
        seen.add(key)
        deduped.append((name, command, cwd))
    return deduped


def _repair_utf8_bom_files(repo_root: Path, syntax_stdout: str) -> VerificationStepResult:
    start = time.perf_counter()
    targets: set[Path] = set()
    for raw_line in syntax_stdout.splitlines():
        line = raw_line.strip()
        if "U+FEFF" not in line or ":" not in line:
            continue
        relative_part = line.split(":", 1)[0].strip()
        candidate = (repo_root / relative_part).resolve()
        if candidate.exists() and candidate.is_file():
            targets.add(candidate)

    fixed = 0
    for path in sorted(targets):
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            path.write_bytes(raw[3:])
            fixed += 1

    elapsed = int((time.perf_counter() - start) * 1000)
    if fixed == 0:
        return VerificationStepResult(
            name="bom_strip",
            command="internal:bom-strip",
            exit_code=1,
            status="ok",
            duration_ms=elapsed,
            stdout="No UTF-8 BOM-prefixed Python files fixed.",
            stderr="",
        )

    return VerificationStepResult(
        name="bom_strip",
        command="internal:bom-strip",
        exit_code=0,
        status="ok",
        duration_ms=elapsed,
        stdout=f"Removed UTF-8 BOM from {fixed} file(s).",
        stderr="",
    )
