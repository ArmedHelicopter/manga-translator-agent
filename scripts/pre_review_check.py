#!/usr/bin/env python3
"""Pre-review automated checks for mga project.

Usage:
    python scripts/pre_review_check.py --all
    python scripts/pre_review_check.py --check imports
    python scripts/pre_review_check.py --check layers
    python scripts/pre_review_check.py --check security
    python scripts/pre_review_check.py --check tests
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


class CheckResult:
    def __init__(self, name: str):
        self.name = name
        self.issues: List[Tuple[str, str, str]] = []  # (severity, file, message)
        
    def add(self, severity: str, file: str, message: str):
        self.issues.append((severity, file, message))
        
    def is_clean(self) -> bool:
        return len(self.issues) == 0
        
    def report(self):
        if self.is_clean():
            print(f"[PASS] {self.name}: CLEAN")
            return
            
        print(f"[FAIL] {self.name}: {len(self.issues)} issue(s)")
        for severity, file, message in self.issues:
            icon = "[ERROR]" if severity == "ERROR" else "[WARNING]"
            print(f"   {icon} {file}: {message}")


def check_layer_boundaries(root: Path) -> CheckResult:
    """Check for cross-layer import violations."""
    result = CheckResult("Layer Boundaries")
    
    # Layer 0 (models) should not import from any other layer
    for f in (root / "mga" / "models").glob("*.py"):
        content = f.read_text(encoding="utf-8")
        if re.search(r"from mga\.(pipeline|providers|memory|cultural|qa|learning|cli|web)", content):
            result.add("ERROR", f.relative_to(root).as_posix(), 
                      "Layer 0 (models) imports from higher layer")
    
    # Layer 1 (infra) should not import from Layer 2+
    for subdir in ["config", "format", "providers"]:
        for f in (root / "mga" / subdir).rglob("*.py"):
            content = f.read_text(encoding="utf-8")
            if re.search(r"from mga\.(memory|cultural|qa|learning|pipeline|cli|web)", content):
                result.add("ERROR", f.relative_to(root).as_posix(),
                          "Layer 1 (infra) imports from Layer 2+")
    
    # Layer 2 (intelligence) should not import from Layer 3+
    for subdir in ["memory", "cultural", "qa", "learning"]:
        for f in (root / "mga" / subdir).rglob("*.py"):
            content = f.read_text(encoding="utf-8")
            if re.search(r"from mga\.(pipeline|cli|web)", content):
                result.add("ERROR", f.relative_to(root).as_posix(),
                          "Layer 2 (intelligence) imports from Layer 3+")
    
    # No layer should import from manga_translator runtime internals
    for f in (root / "mga").rglob("*.py"):
        if f.relative_to(root).as_posix().startswith("mga/runtime_bridge"):
            continue
        content = f.read_text(encoding="utf-8")
        if "from manga_translator" in content and "runtime_bridge" not in f.name:
            result.add("ERROR", f.relative_to(root).as_posix(),
                      f"Imports from manga_translator runtime (should be in runtime_bridge only)")
    
    return result


def check_exception_hierarchy(root: Path) -> CheckResult:
    """Check for proper exception usage."""
    result = CheckResult("Exception Hierarchy")
    
    for f in (root / "mga").rglob("*.py"):
        content = f.read_text(encoding="utf-8")
        
        # Check for bare Exception raises
        if re.search(r'raise Exception\(["\']', content):
            result.add("ERROR", f.relative_to(root).as_posix(),
                      "Uses bare 'raise Exception' instead of domain exception")
        
        # Count bare Exception catches (should be minimal)
        bare_catches = len(re.findall(r'except Exception:', content))
        if bare_catches > 2:
            result.add("WARNING", f.relative_to(root).as_posix(),
                      f"{bare_catches} bare 'except Exception:' blocks (consider specific exceptions)")
    
    return result


def check_security(root: Path) -> CheckResult:
    """Check for security issues."""
    result = CheckResult("Security")
    
    for f in (root / "mga").rglob("*.py"):
        content = f.read_text(encoding="utf-8")
        rel_path = f.relative_to(root).as_posix()
        
        # Hardcoded keys
        if re.search(r'api_key\s*=\s*["\'][^$]', content):
            result.add("ERROR", rel_path, "Possible hardcoded API key")
        
        if re.search(r'password\s*=\s*["\'][^$]', content):
            result.add("ERROR", rel_path, "Possible hardcoded password")
        
        # Command injection
        if re.search(r'subprocess\.(call|run|Popen).*shell=True', content):
            result.add("ERROR", rel_path, "subprocess with shell=True (injection risk)")
        
        # Path traversal in web endpoints
        if "mga/web" in rel_path:
            if re.search(r'path=str\([^)]*dir', content):
                result.add("WARNING", rel_path, "Possible filesystem path exposure in API")
    
    return result


def check_json_parsing_consistency(root: Path) -> CheckResult:
    """Check that all LLM JSON parsing uses unified utility."""
    result = CheckResult("JSON Parsing Consistency")
    
    for f in (root / "mga" / "providers").rglob("*.py"):
        if f.name == "__init__.py":
            continue
        content = f.read_text(encoding="utf-8")
        
        # Look for local _parse_json implementations
        if re.search(r'def _parse_json\(', content):
            # Check if it's using the unified parser
            if "from mga.util import parse_json_from_llm_response" not in content:
                result.add("WARNING", f.relative_to(root).as_posix(),
                          "Has local _parse_json instead of unified parser")
    
    return result


def check_type_annotations(root: Path) -> CheckResult:
    """Check for missing type annotations."""
    result = CheckResult("Type Annotations")
    
    for f in (root / "mga").rglob("*.py"):
        if f.name == "__init__.py":
            continue
        content = f.read_text(encoding="utf-8")
        
        # Check for __future__ annotations
        if "def " in content and "from __future__ import annotations" not in content:
            result.add("WARNING", f.relative_to(root).as_posix(),
                      "Missing 'from __future__ import annotations'")
        
        # Count functions without return type hints (excluding magic methods)
        untyped = re.findall(r'^def \w+\([^)]*\):\s*$', content, re.MULTILINE)
        untyped = [m for m in untyped if not re.search(r'__\w+__', m)]
        if len(untyped) > 3:
            result.add("WARNING", f.relative_to(root).as_posix(),
                      f"{len(untyped)} functions without return type annotations")
    
    return result


def check_tests_runnable(root: Path) -> CheckResult:
    """Check if tests can run."""
    result = CheckResult("Test Execution")
    
    try:
        # Run quick import test
        proc = subprocess.run(
            [sys.executable, "-c", "import mga; from mga.util import parse_json_from_llm_response"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            result.add("ERROR", "mga/__init__.py", f"Import failed: {proc.stderr}")
    except subprocess.TimeoutExpired:
        result.add("ERROR", "mga/__init__.py", "Import test timed out")
    except Exception as e:
        result.add("ERROR", "mga/__init__.py", f"Import test error: {e}")
    
    # Check for pytest
    try:
        subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        result.add("ERROR", "tests/", "pytest not installed")
    
    return result


def check_dependency_versions(root: Path) -> CheckResult:
    """Check dependency version consistency."""
    result = CheckResult("Dependency Versions")
    
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        result.add("ERROR", "pyproject.toml", "Missing pyproject.toml")
        return result
    
    content = pyproject.read_text(encoding="utf-8")
    
    # Extract pinned dependencies
    pinned = {
        "pydantic": re.search(r'pydantic==([0-9.]+)', content),
        "pytest": re.search(r'pytest==([0-9.]+)', content),
        "openai": re.search(r'openai==([0-9.]+)', content),
        "httpx": re.search(r'httpx==([0-9.]+)', content),
    }
    
    # Check installed versions
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=freeze"],
            capture_output=True,
            text=True,
            check=True,
        )
        installed = proc.stdout
        
        for pkg, match in pinned.items():
            if match:
                required_version = match.group(1)
                installed_match = re.search(rf'{pkg}==([0-9.]+)', installed)
                if installed_match:
                    installed_version = installed_match.group(1)
                    if installed_version != required_version:
                        result.add("WARNING", "pyproject.toml",
                                  f"{pkg}: required={required_version}, installed={installed_version}")
    except subprocess.CalledProcessError as e:
        result.add("WARNING", "environment", f"Could not check installed versions: {e}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Pre-review automated checks")
    parser.add_argument("--all", action="store_true", help="Run all checks")
    parser.add_argument("--check", choices=["imports", "layers", "security", "tests", "deps"],
                       help="Run specific check")
    args = parser.parse_args()
    
    root = Path(__file__).parent.parent
    
    checks = []
    
    if args.all or not args.check:
        checks.extend([
            check_layer_boundaries(root),
            check_exception_hierarchy(root),
            check_security(root),
            check_json_parsing_consistency(root),
            check_type_annotations(root),
            check_tests_runnable(root),
            check_dependency_versions(root),
        ])
    else:
        if args.check == "layers":
            checks.append(check_layer_boundaries(root))
        elif args.check == "imports":
            checks.append(check_exception_hierarchy(root))
        elif args.check == "security":
            checks.append(check_security(root))
        elif args.check == "tests":
            checks.append(check_tests_runnable(root))
        elif args.check == "deps":
            checks.append(check_dependency_versions(root))
    
    print("Running pre-review checks...\n")
    
    all_clean = True
    for check in checks:
        check.report()
        if not check.is_clean():
            all_clean = False
    
    print()
    if all_clean:
        print("[PASS] All checks passed!")
        return 0
    else:
        print("[FAIL] Some checks failed. Review issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
