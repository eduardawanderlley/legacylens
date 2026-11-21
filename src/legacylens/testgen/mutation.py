"""Mutation score dos testes gerados, via mutmut 2.x.

Cobertura diz quais linhas rodaram; mutation score diz se os testes
perceberiam uma mudança de comportamento. Este módulo é um wrapper fino
sobre a CLI do mutmut e foi escrito para a série 2.x (`pip install "mutmut<3"`).
Confira o formato do `junitxml` na sua versão antes de confiar nos números.
"""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MutationResult:
    total: int
    killed: int
    survived: int
    other: int  # suspeitos, timeouts e ignorados

    @property
    def score(self) -> float | None:
        considered = self.killed + self.survived
        return self.killed / considered if considered else None


def parse_junit(xml_text: str) -> MutationResult:
    root = ET.fromstring(xml_text)
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise ValueError("junitxml sem <testsuite>")
    total = int(suite.get("tests", 0))
    survived = int(suite.get("failures", 0))
    other = int(suite.get("errors", 0)) + int(suite.get("skipped", 0))
    return MutationResult(total, total - survived - other, survived, other)


def run_mutation(repo: Path, source_file: str, test_file: Path, timeout: int = 900) -> MutationResult:
    runner = f"{sys.executable} -m pytest -x -q --no-header -p no:cacheprovider {test_file}"
    run = [sys.executable, "-m", "mutmut", "run", "--paths-to-mutate", source_file, "--runner", runner]
    # mutmut sai com código != 0 quando sobram mutantes vivos; isso não é erro.
    subprocess.run(run, cwd=repo, capture_output=True, text=True, timeout=timeout)
    xml = subprocess.run([sys.executable, "-m", "mutmut", "junitxml"], cwd=repo, capture_output=True, text=True, timeout=60)
    if not xml.stdout.strip():
        raise RuntimeError(f"mutmut não produziu resultados: {xml.stderr.strip()[:300]}")
    return parse_junit(xml.stdout)
