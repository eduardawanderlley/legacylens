from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RunResult:
    passed: bool
    output: str
    timed_out: bool = False


class Runner(Protocol):
    def run(self, test_file: Path, cwd: Path) -> RunResult: ...


class PytestRunner:
    """Executa um arquivo de teste em subprocesso, com timeout.

    Isto NÃO é um sandbox de segurança. Código gerado por LLM roda com as
    permissões do seu usuário; em CI ou com repositórios que você não
    controla, rode dentro do container (ver docs/architecture.md).
    """

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    def run(self, test_file: Path, cwd: Path) -> RunResult:
        env = dict(os.environ)
        extra = [str(cwd), str(cwd / "src")]
        env["PYTHONPATH"] = os.pathsep.join(extra + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        cmd = [sys.executable, "-m", "pytest", str(test_file), "-x", "-q", "--no-header", "-p", "no:cacheprovider"]
        try:
            proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            partial = (exc.stdout or b"")
            partial = partial.decode() if isinstance(partial, bytes) else partial
            return RunResult(False, f"Timeout após {self.timeout}s.\n{partial}", timed_out=True)
        return RunResult(proc.returncode == 0, (proc.stdout + proc.stderr).strip())
