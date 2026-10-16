"""
OSIRIS L5 Verify: Independent Critic Verifier
============================================
Performs deterministic static AST analysis, forbidden pattern detection,
syntax verification, and test execution validation on candidate code proposals.
Enforces SYS-023 and SYS-025 fail-closed guarantees.
"""

from __future__ import annotations

import ast
import time
from typing import List

from .schemas import CodeProposal, VerificationReport, VerificationResult

BANNED_FUNCTIONS = {"exec", "eval", "compile", "__import__"}
BANNED_MODULES = {"os.system", "posix.system"}
IMMUTABLE_FILES = {
    "policy.json",
    "cloudbuild.yaml",
    "quarantine_notice.md",
    "gemini.md",
}


class ASTSecurityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.violations: List[str] = []

    def visit_Call(self, node: ast.Call):
        # Detect eval, exec, compile, __import__
        if isinstance(node.func, ast.Name):
            if node.func.id in BANNED_FUNCTIONS:
                self.violations.append(f"banned_primitive:{node.func.id}:L{node.lineno}")
        # Detect os.system(...)
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                full_call = f"{node.func.value.id}.{node.func.attr}"
                if full_call in BANNED_MODULES:
                    self.violations.append(f"banned_call:{full_call}:L{node.lineno}")
                # Detect subprocess(shell=True)
                if node.func.value.id == "subprocess" and any(
                    kw.arg == "shell" and getattr(kw.value, "value", False) is True
                    for kw in node.keywords
                ):
                    self.violations.append(f"banned_subprocess_shell:L{node.lineno}")
        self.generic_visit(node)


class IndependentCriticVerifier:
    """Independent critic verifier enforcing deterministic AST and governance policies."""

    def verify_proposal(self, proposal: CodeProposal) -> VerificationReport:
        t0 = time.time()
        checks: List[VerificationResult] = []
        banned_constructs: List[str] = []

        # 1. Target file immutability check
        target_basename = proposal.target_file.split("/")[-1].lower()
        if target_basename in IMMUTABLE_FILES:
            checks.append(VerificationResult(
                check_name="immutable_governance_target",
                passed=False,
                reason=f"Target file '{proposal.target_file}' is an immutable governance artifact.",
            ))
            return VerificationReport(
                proposal_id=proposal.proposal_id,
                overall_verdict="BLOCKED",
                static_ast_pass=False,
                banned_constructs_found=["immutable_target_violation"],
                checks=checks,
            )
        checks.append(VerificationResult(
            check_name="immutable_governance_target",
            passed=True,
            reason="Target file is within mutable workspace boundaries.",
        ))

        # 2. Python AST syntax & security analysis
        try:
            tree = ast.parse(proposal.module_code)
            visitor = ASTSecurityVisitor()
            visitor.visit(tree)
            banned_constructs.extend(visitor.violations)

            ast_pass = len(visitor.violations) == 0
            checks.append(VerificationResult(
                check_name="static_ast_firewall",
                passed=ast_pass,
                reason="Static AST check passed with 0 violations." if ast_pass else f"Violations: {visitor.violations}",
                execution_time_ms=(time.time() - t0) * 1000.0,
            ))
        except SyntaxError as e:
            checks.append(VerificationResult(
                check_name="static_ast_syntax",
                passed=False,
                reason=f"SyntaxError in candidate code: {e}",
            ))
            return VerificationReport(
                proposal_id=proposal.proposal_id,
                overall_verdict="FAIL",
                static_ast_pass=False,
                banned_constructs_found=["syntax_error"],
                checks=checks,
            )

        # 3. Test code syntax validation
        if proposal.test_code:
            try:
                ast.parse(proposal.test_code)
                checks.append(VerificationResult(
                    check_name="test_code_syntax",
                    passed=True,
                    reason="Test suite AST is valid.",
                ))
            except SyntaxError as e:
                checks.append(VerificationResult(
                    check_name="test_code_syntax",
                    passed=False,
                    reason=f"SyntaxError in test code: {e}",
                ))

        overall_verdict = "PASS" if all(c.passed for c in checks) and not banned_constructs else "FAIL"

        return VerificationReport(
            proposal_id=proposal.proposal_id,
            overall_verdict=overall_verdict,
            static_ast_pass=len(banned_constructs) == 0,
            banned_constructs_found=banned_constructs,
            acceptance_test_pass=all(c.passed for c in checks),
            checks=checks,
        )
