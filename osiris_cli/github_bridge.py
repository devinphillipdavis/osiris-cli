"""
OSIRIS GitHub Bridge & PR Management Subsystem
=============================================
Provides governed CLI and REPL access to GitHub repositories and PR workflows.
Enforces OSIRIS Dual-Node Governance:
  - Read-Only / Inspection Tier: `gh auth status`, `gh pr list`, `gh pr view`, `gh repo list`
  - Mutating / State-Advancing Tier: `gh pr create`, `gh pr merge`, `git push`
    Strictly gated behind SYS-021 payload-bound authorization grants.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Union


class GitHubBridge:
    """Governed GitHub CLI interface for OSIRIS."""

    def __init__(self, gh_binary: Optional[str] = None):
        self.gh_binary = gh_binary or shutil.which("gh")

    def is_installed(self) -> bool:
        return self.gh_binary is not None

    def check_auth(self) -> Dict[str, Any]:
        """Check authentication status with GitHub CLI."""
        if not self.is_installed():
            return {
                "installed": False,
                "authenticated": False,
                "reason": "GitHub CLI ('gh') is not installed in the current environment PATH."
            }

        try:
            res = subprocess.run(
                [self.gh_binary, "auth", "status"],
                capture_output=True,
                text=True,
                check=False
            )
            # gh auth status exits 0 when fully authenticated
            is_auth = (res.returncode == 0)
            combined_output = (res.stdout or "") + (res.stderr or "")
            account = "unknown"
            scopes = []
            for line in combined_output.splitlines():
                line_s = line.strip()
                if "account" in line_s:
                    parts = line_s.split()
                    if "account" in parts:
                        idx = parts.index("account")
                        if idx + 1 < len(parts):
                            account = parts[idx + 1]
                if "Token scopes:" in line_s:
                    scopes_raw = line_s.split("Token scopes:", 1)[1].strip()
                    scopes = [s.strip(" '\"") for s in scopes_raw.split(",")]

            return {
                "installed": True,
                "authenticated": is_auth,
                "account": account,
                "scopes": scopes,
                "raw": combined_output.strip()
            }
        except Exception as e:
            return {
                "installed": True,
                "authenticated": False,
                "reason": f"Execution error probing gh auth status: {e}"
            }

    def list_prs(self, limit: int = 10) -> Dict[str, Any]:
        """List open pull requests (Read-Only tier)."""
        if not self.is_installed():
            return {"status": "ERROR", "reason": "gh CLI not installed"}

        try:
            cmd = [
                self.gh_binary, "pr", "list",
                "--limit", str(limit),
                "--json", "number,title,state,headRefName,url,updatedAt"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                return {"status": "ERROR", "reason": res.stderr.strip() or "Failed to list PRs"}
            prs = json.loads(res.stdout) if res.stdout.strip() else []
            return {"status": "SUCCESS", "prs": prs}
        except Exception as e:
            return {"status": "ERROR", "reason": str(e)}

    def view_pr(self, pr_id: Union[int, str]) -> Dict[str, Any]:
        """View PR details avoiding classic projectCards GraphQL issues (Read-Only tier)."""
        if not self.is_installed():
            return {"status": "ERROR", "reason": "gh CLI not installed"}

        try:
            cmd = [
                self.gh_binary, "pr", "view", str(pr_id),
                "--json", "number,title,state,headRefName,baseRefName,url,body"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                return {"status": "ERROR", "reason": res.stderr.strip() or f"Failed to view PR #{pr_id}"}
            pr_data = json.loads(res.stdout) if res.stdout.strip() else {}
            return {"status": "SUCCESS", "pr": pr_data}
        except Exception as e:
            return {"status": "ERROR", "reason": str(e)}

    def checks_pr(self, pr_id: Union[int, str]) -> Dict[str, Any]:
        """View CI/CD check runs for a PR (Read-Only tier)."""
        if not self.is_installed():
            return {"status": "ERROR", "reason": "gh CLI not installed"}

        try:
            cmd = [self.gh_binary, "pr", "checks", str(pr_id)]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            return {
                "status": "SUCCESS" if res.returncode == 0 else "FAILED",
                "output": (res.stdout or res.stderr).strip()
            }
        except Exception as e:
            return {"status": "ERROR", "reason": str(e)}

    def list_repos(self, limit: int = 10) -> Dict[str, Any]:
        """List repositories for authenticated user (Read-Only tier)."""
        if not self.is_installed():
            return {"status": "ERROR", "reason": "gh CLI not installed"}

        try:
            cmd = [
                self.gh_binary, "repo", "list",
                "--limit", str(limit),
                "--json", "nameWithOwner,isPrivate,updatedAt,url"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                return {"status": "ERROR", "reason": res.stderr.strip() or "Failed to list repos"}
            repos = json.loads(res.stdout) if res.stdout.strip() else []
            return {"status": "SUCCESS", "repos": repos}
        except Exception as e:
            return {"status": "ERROR", "reason": str(e)}

    def merge_pr(self, pr_id: Union[int, str], grant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Merge a pull request.
        MUTATING / STATE-ADVANCING: strictly requires SYS-021 payload-bound grant.
        """
        if not grant_id or not grant_id.strip():
            return {
                "status": "BLOCKED",
                "reason": (
                    "[SYS-021 BLOCKED] Bare merge directives forbidden. "
                    "Provide explicit payload-bound grant_id binding PR digest."
                )
            }
        return {
            "status": "HOLD",
            "reason": f"Grant {grant_id} registered. Remote merge held for human review."
        }

    def format_dashboard(self) -> str:
        """Format a human-readable GitHub governance card for REPL / CLI."""
        lines = []
        lines.append("\033[1;36m[OSIRIS::GITHUB REPOSITORY & PR SUBSYSTEM]\033[0m")
        auth = self.check_auth()
        if not auth["installed"]:
            lines.append("  \033[1;31mGitHub CLI ('gh') is not installed in PATH.\033[0m")
            return "\n".join(lines)

        if not auth["authenticated"]:
            lines.append("  \033[1;33mGitHub CLI installed but not authenticated. Run 'gh auth login'.\033[0m")
            return "\n".join(lines)

        account = auth.get("account", "unknown")
        scopes = ", ".join(auth.get("scopes", [])) or "default"
        lines.append(f"  ├─ Authenticated Account : \033[1;32m{account}\033[0m")
        lines.append(f"  ├─ Authorized Scopes    : {scopes}")
        lines.append("  ├─ Governance Tier      : Read-Only (Inspection Active · Mutating Ops Gated)")

        pr_res = self.list_prs(limit=5)
        if pr_res["status"] == "SUCCESS" and pr_res["prs"]:
            lines.append("  └─ Open Pull Requests   :")
            for pr in pr_res["prs"]:
                num = pr.get("number", "?")
                title = pr.get("title", "")
                head = pr.get("headRefName", "")
                lines.append(f"     • \033[1;37m#{num}\033[0m: {title} (\033[1;34m{head}\033[0m)")
        elif pr_res["status"] == "SUCCESS":
            lines.append("  └─ Open Pull Requests   : None currently open")
        else:
            lines.append(f"  └─ Pull Requests Error  : {pr_res.get('reason')}")

        return "\n".join(lines)
