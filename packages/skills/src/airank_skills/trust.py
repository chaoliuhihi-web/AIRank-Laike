from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping

from .registry import SkillManifest, SkillRegistry, load_default_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PACKAGE_ROOT.parents[1]
CORE_SOURCE = Path(__file__).with_name("core.py")
INTERNAL_PACKAGE_SOURCES = {
    "airank_skills": PACKAGE_ROOT / "src" / "airank_skills",
    "airank_domain": REPOSITORY_ROOT / "packages" / "domain" / "src" / "airank_domain",
    "airank_score": REPOSITORY_ROOT / "packages" / "score" / "src" / "airank_score",
}
SECRET_PATTERNS = (
    "sk-",
    "-----begin private key-----",
    "bearer eyj",
    "akia",
)
NETWORK_ROOTS = {"aiohttp", "httpx", "requests", "socket", "urllib", "urllib3", "websocket", "websockets"}
FILESYSTEM_CALLS = {
    "open",
    "os.mkdir",
    "os.makedirs",
    "os.open",
    "os.remove",
    "os.rename",
    "os.replace",
    "os.rmdir",
    "os.unlink",
    "pathlib.Path.mkdir",
    "pathlib.Path.open",
    "pathlib.Path.rename",
    "pathlib.Path.replace",
    "pathlib.Path.rmdir",
    "pathlib.Path.touch",
    "pathlib.Path.unlink",
    "pathlib.Path.write_bytes",
    "pathlib.Path.write_text",
    "shutil.copy",
    "shutil.copy2",
    "shutil.copyfile",
    "shutil.copytree",
    "shutil.move",
    "shutil.rmtree",
}
SUBPROCESS_CALLS = {"os.popen", "os.spawn", "os.system", "subprocess.call", "subprocess.Popen", "subprocess.run"}
SECRET_CALLS = {"os.getenv"}
DYNAMIC_CODE_CALLS = {"__import__", "eval", "exec", "importlib.import_module"}
REQUIRED_ADMIN_PERMISSION = "airank:skill:admin"


def stable_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _module_tree(source_text: str) -> ast.Module:
    return ast.parse(source_text)


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _import_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".", 1)[0]] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    return aliases


def _apply_import_alias(call_name: str, aliases: Mapping[str, str]) -> str:
    root, separator, suffix = call_name.partition(".")
    resolved_root = aliases.get(root, root)
    return f"{resolved_root}.{suffix}" if separator else resolved_root


def inspect_runner_capabilities(source_text: str, runner_name: str) -> dict[str, list[str]]:
    """Statically inspect a runner and its local helper-call closure.

    This is an executable repository gate, not an OS sandbox. Dynamic imports and
    monkey-patched callables remain outside this claim and are reported separately.
    """

    tree = _module_tree(source_text)
    functions = _module_functions(tree)
    aliases = _import_aliases(tree)
    if runner_name not in functions:
        return {
            "network": [],
            "filesystem": [],
            "subprocess": [],
            "secret": [],
            "dynamic_code": [],
            "missing_runner": [runner_name],
        }

    observed: dict[str, set[str]] = {
        "network": set(),
        "filesystem": set(),
        "subprocess": set(),
        "secret": set(),
        "dynamic_code": set(),
    }
    pending = [runner_name]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        function = functions[current]
        for node in ast.walk(function):
            if isinstance(node, ast.Call):
                call_name = _apply_import_alias(_dotted_name(node.func), aliases)
                root = call_name.split(".", 1)[0]
                if root in NETWORK_ROOTS:
                    observed["network"].add(call_name)
                if (
                    call_name in FILESYSTEM_CALLS
                    or call_name.rsplit(".", 1)[-1]
                    in {"mkdir", "rmdir", "touch", "unlink", "write_bytes", "write_text"}
                ):
                    observed["filesystem"].add(call_name)
                if call_name in SUBPROCESS_CALLS or root == "subprocess":
                    observed["subprocess"].add(call_name)
                if call_name in SECRET_CALLS or call_name.startswith("os.environ"):
                    observed["secret"].add(call_name)
                if call_name in DYNAMIC_CODE_CALLS:
                    observed["dynamic_code"].add(call_name)
                if call_name in functions and call_name not in visited:
                    pending.append(call_name)
            elif isinstance(node, ast.Subscript):
                target = _dotted_name(node.value)
                if target in {"os.environ", "environ"}:
                    observed["secret"].add(target)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.lower()
                if any(pattern in lowered and len(node.value) >= 20 for pattern in SECRET_PATTERNS):
                    observed["secret"].add("embedded_secret_literal")
    return {name: sorted(values) for name, values in observed.items()}


def _check(check_id: str, passed: bool, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": "passed" if passed else "failed",
        "details": dict(details or {}),
    }


def _dependency_is_safe(reference: Mapping[str, Any]) -> bool:
    values = [str(reference.get(key) or "") for key in ("dependency", "target")]
    return all(
        value
        and "://" not in value
        and "/" not in value
        and "\\" not in value
        and ".." not in value
        and not any(marker in value for marker in (";", "$", "`", "\n", "\r"))
        for value in values
    )


def _resolve_dependency(reference: Mapping[str, Any], registry: SkillRegistry) -> bool:
    kind = str(reference.get("kind") or "")
    target = str(reference.get("target") or "")
    try:
        if kind == "python_module":
            importlib.import_module(target)
        elif kind == "python_symbol":
            module_name, symbol_name = target.split(":", 1)
            if not hasattr(importlib.import_module(module_name), symbol_name):
                return False
        elif kind == "skill_contract":
            registry.get(target)
        else:
            return False
    except (ImportError, KeyError, ValueError):
        return False
    return True


def _entrypoint_result(manifest: SkillManifest) -> tuple[bool, str]:
    try:
        module_name, function_name = manifest.entrypoint.split(":", 1)
        function = getattr(importlib.import_module(module_name), function_name)
    except (ImportError, AttributeError, ValueError):
        return False, "unresolvable"
    return callable(function), f"{module_name}:{function_name}"


def _contains_secret_literal(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_secret_literal(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_secret_literal(item) for item in value)
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return any(pattern in lowered and len(value) >= 20 for pattern in SECRET_PATTERNS)


@dataclass(frozen=True)
class SkillTrustAudit:
    skill_id: str
    version: str
    decision: str
    policy_sha256: str
    implementation_sha256: str
    observed_capabilities: Mapping[str, list[str]]
    checks: tuple[Mapping[str, Any], ...]

    @property
    def execution_allowed(self) -> bool:
        return self.decision == "allow_local_execution"

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "version": self.version,
            "decision": self.decision,
            "execution_allowed": self.execution_allowed,
            "policy_sha256": self.policy_sha256,
            "implementation_sha256": self.implementation_sha256,
            "observed_capabilities": dict(self.observed_capabilities),
            "checks": [dict(item) for item in self.checks],
        }


def audit_manifest(
    manifest: SkillManifest,
    registry: SkillRegistry,
    *,
    source_text: str | None = None,
) -> SkillTrustAudit:
    policy = manifest.trust_policy
    dependency_refs = tuple(policy.get("dependency_refs", ()))
    declared_dependencies = {str(value) for value in manifest.dependencies}
    referenced_dependencies = {str(item.get("dependency") or "") for item in dependency_refs}
    dependency_declarations_match = declared_dependencies == referenced_dependencies
    dependency_specs_safe = all(_dependency_is_safe(item) for item in dependency_refs)
    dependencies_resolve = all(_resolve_dependency(item, registry) for item in dependency_refs)

    entrypoint_ok, entrypoint = _entrypoint_result(manifest)
    runner_name = manifest.entrypoint.rsplit(":", 1)[-1]
    implementation_text = source_text if source_text is not None else CORE_SOURCE.read_text(encoding="utf-8")
    observed = inspect_runner_capabilities(implementation_text, runner_name)
    network_mode = str(policy.get("network_access", {}).get("mode") or "")
    filesystem_mode = str(policy.get("filesystem_access", {}).get("mode") or "")
    secret_mode = str(policy.get("secret_access", {}).get("mode") or "")
    capability_policy_ok = (
        not observed.get("missing_runner")
        and not observed["subprocess"]
        and not observed["dynamic_code"]
        and (network_mode != "deny" or not observed["network"])
        and (filesystem_mode != "deny" or not observed["filesystem"])
        and (secret_mode != "deny" or not observed["secret"])
    )
    no_embedded_secret = not _contains_secret_literal(policy)
    required_permissions = tuple(str(value) for value in policy.get("required_permissions", ()))
    permission_ok = REQUIRED_ADMIN_PERMISSION in required_permissions
    install_policy = policy.get("install_policy", {})
    package_roots = tuple(str(value) for value in install_policy.get("internal_package_roots", ()))
    package_policy_ok = (
        "airank_skills" in package_roots
        and all(root in INTERNAL_PACKAGE_SOURCES for root in package_roots)
        and install_policy.get("allow_repository_imports") is False
    )
    status_allows_eval = manifest.status not in {"blocked", "disabled"}
    checks = (
        _check(
            "dependency_declarations",
            dependency_declarations_match and dependency_specs_safe,
            {
                "declared_count": len(declared_dependencies),
                "reference_count": len(referenced_dependencies),
                "unsafe_reference_count": sum(not _dependency_is_safe(item) for item in dependency_refs),
            },
        ),
        _check("dependency_resolution", dependencies_resolve, {"resolved_count": sum(_resolve_dependency(item, registry) for item in dependency_refs)}),
        _check("entrypoint_resolution", entrypoint_ok, {"entrypoint": entrypoint}),
        _check("declared_capability_boundary", capability_policy_ok, {"runtime_mode": policy.get("runtime_mode")}),
        _check("secret_literal_scan", no_embedded_secret, {"secret_value_stored": not no_embedded_secret}),
        _check("admin_permission_declaration", permission_ok, {"required_permission": REQUIRED_ADMIN_PERMISSION}),
        _check("isolated_install_declaration", package_policy_ok, {"package_roots": list(package_roots)}),
        _check("manifest_status", status_allows_eval, {"manifest_status": manifest.status}),
    )
    allowed = all(item["status"] == "passed" for item in checks)
    return SkillTrustAudit(
        skill_id=manifest.skill_id,
        version=manifest.version,
        decision="allow_local_execution" if allowed else "block_execution",
        policy_sha256=stable_sha256(policy),
        implementation_sha256=hashlib.sha256(implementation_text.encode("utf-8")).hexdigest(),
        observed_capabilities=observed,
        checks=checks,
    )


def _iter_package_files(package_roots: Iterable[str]) -> Iterable[tuple[Path, Path]]:
    for root_name in sorted(set(package_roots)):
        source_root = INTERNAL_PACKAGE_SOURCES[root_name]
        relative_root = source_root.relative_to(REPOSITORY_ROOT)
        for source in sorted(source_root.rglob("*.py")):
            yield source, relative_root / source.relative_to(source_root)
    for source in (PACKAGE_ROOT / "registry.json", PACKAGE_ROOT / "registry.schema.json"):
        yield source, source.relative_to(REPOSITORY_ROOT)


def external_dependency_paths(dependency_names: Iterable[str]) -> tuple[str, ...]:
    paths: set[str] = set()
    for dependency_name in sorted(set(dependency_names)):
        spec = importlib.util.find_spec(dependency_name)
        if spec is None:
            continue
        if spec.submodule_search_locations:
            for location in spec.submodule_search_locations:
                paths.add(str(Path(location).resolve().parent))
        elif spec.origin:
            paths.add(str(Path(spec.origin).resolve().parent))
    return tuple(sorted(paths))


def simulate_isolated_install(registry: SkillRegistry) -> dict[str, Any]:
    package_roots = {
        str(root)
        for manifest in registry.list()
        for root in manifest.trust_policy.get("install_policy", {}).get("internal_package_roots", ())
    }
    external_dependencies = {
        str(dependency)
        for manifest in registry.list()
        for dependency in manifest.trust_policy.get("install_policy", {}).get("external_python_dependencies", ())
    }
    copied_hashes: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="airank-skill-install-") as temp_value:
        temp_root = Path(temp_value)
        for source, relative in _iter_package_files(package_roots):
            destination = temp_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied_hashes[relative.as_posix()] = file_sha256(destination)

        package_paths = [str(temp_root / "packages" / "skills" / "src")]
        for root_name in sorted(package_roots - {"airank_skills"}):
            package_paths.append(str(temp_root / "packages" / root_name.removeprefix("airank_").replace("_", "-") / "src"))
        package_paths.extend(external_dependency_paths(external_dependencies))
        blocked_roots = [
            str(REPOSITORY_ROOT),
            str(REPOSITORY_ROOT / "apps"),
            str(REPOSITORY_ROOT / "packages"),
        ]
        probe = """
import importlib
import json
from pathlib import Path
import sys
paths = json.loads(sys.argv[1])
blocked_roots = [Path(value).resolve() for value in json.loads(sys.argv[2])]
def repository_source(path):
    try:
        candidate = Path(path or '.').resolve()
    except OSError:
        return True
    if candidate == blocked_roots[0]:
        return True
    return any(root == candidate or root in candidate.parents for root in blocked_roots[1:])
sys.path[:] = paths + [path for path in sys.path if not repository_source(path)]
from airank_skills import load_default_registry
registry = load_default_registry()
resolved = []
for manifest in registry.list():
    module_name, function_name = manifest.entrypoint.split(':', 1)
    function = getattr(importlib.import_module(module_name), function_name)
    if not callable(function):
        raise TypeError(manifest.entrypoint)
    for reference in manifest.trust_policy['dependency_refs']:
        target = reference['target']
        if reference['kind'] == 'python_module':
            importlib.import_module(target)
        elif reference['kind'] == 'python_symbol':
            dependency_module, symbol_name = target.split(':', 1)
            if not hasattr(importlib.import_module(dependency_module), symbol_name):
                raise AttributeError(target)
        elif reference['kind'] == 'skill_contract':
            registry.get(target)
    resolved.append(manifest.skill_id)
print(json.dumps({'skill_count': len(resolved), 'skills': sorted(resolved)}))
"""
        environment = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
        result = subprocess.run(
            [sys.executable, "-S", "-c", probe, json.dumps(package_paths), json.dumps(blocked_roots)],
            cwd=temp_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        payload: dict[str, Any] = {}
        if result.returncode == 0:
            try:
                payload = json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                payload = {}
        passed = result.returncode == 0 and payload.get("skill_count") == len(registry.list())
        return {
            "status": "passed" if passed else "failed",
            "isolated_from_repository_imports": passed,
            "skill_count": int(payload.get("skill_count") or 0),
            "package_file_count": len(copied_hashes),
            "package_manifest_sha256": stable_sha256(copied_hashes),
            "failure": None if passed else (result.stderr.strip()[-800:] or "isolated import probe failed"),
        }


def build_trust_report(
    registry: SkillRegistry | None = None,
    *,
    run_install_simulation: bool = True,
) -> dict[str, Any]:
    selected_registry = registry or load_default_registry()
    audits = tuple(audit_manifest(manifest, selected_registry) for manifest in selected_registry.list())
    installation = (
        simulate_isolated_install(selected_registry)
        if run_install_simulation
        else {
            "status": "not_run",
            "isolated_from_repository_imports": False,
            "skill_count": 0,
            "package_file_count": 0,
            "package_manifest_sha256": None,
            "failure": "install simulation was not requested",
        }
    )
    blocked_count = sum(not audit.execution_allowed for audit in audits)
    status = "passed" if blocked_count == 0 and installation["status"] == "passed" else "failed"
    report: dict[str, Any] = {
        "contract_version": "airank.skill-trust-report.v1",
        "status": status,
        "claim_level": "repository_gate_only",
        "native_runtime_enforcement": False,
        "limitations": [
            "static capability inspection cannot prove OS-level sandboxing",
            "isolated import simulation does not replace production worker permission enforcement",
            "provider calls and evidence storage remain outside deterministic Skill runners",
        ],
        "summary": {
            "skill_count": len(audits),
            "execution_allowed_count": len(audits) - blocked_count,
            "blocked_count": blocked_count,
            "install_simulation_status": installation["status"],
        },
        "installation": installation,
        "skills": [audit.to_dict() for audit in audits],
        "source_sha256": {
            "registry": file_sha256(PACKAGE_ROOT / "registry.json"),
            "registry_schema": file_sha256(PACKAGE_ROOT / "registry.schema.json"),
            "implementation": file_sha256(CORE_SOURCE),
            "trust_engine": file_sha256(Path(__file__)),
        },
    }
    report["report_sha256"] = stable_sha256(report)
    return report


def trust_allows_skill(skill_id: str, registry: SkillRegistry | None = None) -> tuple[bool, SkillTrustAudit]:
    selected_registry = registry or load_default_registry()
    manifest = selected_registry.get(skill_id)
    audit = audit_manifest(manifest, selected_registry)
    return audit.execution_allowed, audit
