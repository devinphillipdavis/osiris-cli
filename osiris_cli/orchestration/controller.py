"""
OSIRIS Governance Controller
============================
Enforces deterministic policy invariants:
  - SYS-021: Payload-Bound Authorization (H_payload digest binding)
  - SYS-025: Static AST Firewall analysis and immutable file protection
Deterministic code decides; models propose.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
from typing import List, Optional, Set, Tuple

from .schemas import CodeProposal, ExecutionGrant, VerificationReport, VerificationResult

# Invariant SYS-025: Banned AST calls for unconstrained execution
BANNED_CALL_NAMES = {
    "exec",
    "eval",
    "compile",
    "__import__",
}

# Immutable governance artifacts targeted mutations trigger immediate fail-closed termination
IMMUTABLE_GOVERNANCE_FILES = {
    "policy.json",
    "cloudbuild.yaml",
    "quarantine_notice.md",
    "gemini.md",
    ".osiris_compliance",
}


class ASTFirewallVisitor(ast.NodeVisitor):
    """Inspects AST nodes for unconstrained execution primitives (SYS-025)."""

    def __init__(self):
        self.violations: List[str] = []

    def visit_Call(self, node: ast.Call):
        func = node.func
        # Check direct calls (e.g. exec(...), eval(...))
        if isinstance(func, ast.Name):
            if func.id in BANNED_CALL_NAMES:
                self.violations.append(f"Forbidden call: '{func.id}' at line {node.lineno}")

        # Check attribute calls (e.g. os.system, subprocess.Popen)
        elif isinstance(func, ast.Attribute):
            attr_name = func.attr
            # Detect os.system, os.popen
            if isinstance(func.value, ast.Name) and func.value.id == "os":
                if attr_name in ("system", "popen", "execv", "execve", "spawnl"):
                    self.violations.append(f"Forbidden os call: 'os.{attr_name}' at line {node.lineno}")

            # Detect subprocess(shell=True)
            elif isinstance(func.value, ast.Name) and func.value.id in ("subprocess", "sp"):
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        self.violations.append(f"Forbidden subprocess with shell=True at line {node.lineno}")

        self.generic_visit(node)


class GovernanceController:
    """Deterministic policy gatekeeper."""

    @staticmethod
    def inspect_ast(source_code: str) -> Tuple[bool, List[str]]:
        """Static AST security analysis. Returns (is_clean, violations)."""
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return False, [f"SyntaxError in candidate code: {e}"]

        visitor = ASTFirewallVisitor()
        visitor.visit(tree)
        if visitor.violations:
            return False, visitor.violations
        return True, []

    @staticmethod
    def verify_target_scope(target_file: str, allowed_paths: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Check target file is not an immutable governance file and resides in allowed scope.

        Paths are compared after resolving symlinks, so a link inside the scope cannot point a
        write outside it or at a governance file. With no scope given, the scope is the working
        directory -- the same safe root the REPL's own write check uses -- never "anywhere".
        """
        resolved = os.path.realpath(target_file)
        for name in {os.path.basename(target_file).lower(), os.path.basename(resolved).lower()}:
            if name in IMMUTABLE_GOVERNANCE_FILES:
                return False, f"Target '{target_file}' is an immutable governance artifact (SYS-025 violation)"

        roots = list(allowed_paths) if allowed_paths else ["."]
        for p in roots:
            root = os.path.realpath(p)
            if resolved == root or resolved.startswith(root.rstrip(os.sep) + os.sep):
                return True, "Scope valid"
        return False, f"Target '{target_file}' outside permitted scope {roots}"

    @staticmethod
    def authorize_execution(
        proposal: CodeProposal,
        grant: Optional[ExecutionGrant],
        allowed_paths: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """
        Authorize execution under SYS-021 and SYS-025.
        Fails closed on missing/invalid grant, hash mismatch, or AST violation.
        """
        # 1. Target scope check
        scope_ok, scope_msg = GovernanceController.verify_target_scope(proposal.target_file, allowed_paths)
        if not scope_ok:
            return False, f"AUTHORIZATION_REJECTED: {scope_msg}"

        # 2. Static AST check
        ast_ok, ast_violations = GovernanceController.inspect_ast(proposal.module_code)
        if not ast_ok:
            return False, f"AUTHORIZATION_REJECTED (SYS-025): Banned constructs {ast_violations}"

        # 3. Payload-bound grant verification (SYS-021)
        if grant is None:
            return False, "AUTHORIZATION_REJECTED (SYS-021): Missing execution grant"

        candidate_digest = proposal.payload_digest()
        if not grant.is_valid(candidate_digest):
            return False, (
                f"AUTHORIZATION_REJECTED (SYS-021): Grant digest mismatch or expired. "
                f"Expected: {grant.payload_digest[:16]}..., Actual: {candidate_digest[:16]}..."
            )

        return True, "AUTHORIZED"
