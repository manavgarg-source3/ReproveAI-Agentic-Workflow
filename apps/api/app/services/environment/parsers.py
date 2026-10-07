"""Deterministic, non-executing parsers for bounded environment evidence."""

from __future__ import annotations

import re
import shlex
import tomllib
import configparser
import json
from dataclasses import dataclass, field

from app.schemas.research import Certainty, DependencyType, EnvironmentDependency, EnvironmentEvidence


_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_OPERATOR = r"===|==|~=|!=|<=|>=|<|>"
_REQUIREMENT = re.compile(
    rf"^(?P<name>{_NAME})(?:\[(?P<extras>[A-Za-z0-9_,.-]+)\])?"
    rf"\s*(?P<constraints>(?:(?:{_OPERATOR})\s*[^,;\s]+)"
    rf"(?:\s*,\s*(?:{_OPERATOR})\s*[^,;\s]+)*)?"
    r"\s*(?:;\s*(?P<marker>[^;]+))?$"
)
_DIRECT_REFERENCE = re.compile(rf"^(?P<name>{_NAME})\s*@\s*(?P<url>https?://\S+)$")
_SECRET_NAME = re.compile(
    r"(?:^|_)(?:API_KEY|PRIVATE_KEY|KEY|TOKEN|SECRET|PASSWORD|PASS|PWD|"
    r"CREDENTIAL|AUTH)(?:$|_)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DockerfileData:
    base_image: str | None = None
    operating_system: str | None = None
    operating_system_version: str | None = None
    python_version: str | None = None
    cuda_version: str | None = None
    cudnn_version: str | None = None
    system_dependencies: list[str] = field(default_factory=list)
    environment_variables: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    working_directory: str | None = None
    evidence: list[EnvironmentEvidence] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DocumentationData:
    evidence: list[EnvironmentEvidence] = field(default_factory=list)
    environment_variables: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    system_dependencies: list[str] = field(default_factory=list)


def is_secret_variable(name: str) -> bool:
    return bool(_SECRET_NAME.search(name.strip()))


def _dependency(
    name: str,
    constraint: str | None,
    source_path: str,
    evidence: str,
    *,
    dependency_type: DependencyType = DependencyType.PYTHON_PACKAGE,
) -> EnvironmentDependency:
    return EnvironmentDependency(
        name=name,
        version_constraint=constraint,
        dependency_type=dependency_type,
        source_path=source_path,
        evidence=evidence.strip(),
        certainty=Certainty.EXPLICIT,
    )


def parse_requirement_line(line: str, source_path: str) -> EnvironmentDependency | None:
    """Parse one recognizable PEP 508-style requirement."""

    candidate = line.split("#", 1)[0].strip()
    if not candidate or candidate.startswith(("-", "http://", "https://", "git+")):
        return None
    direct = _DIRECT_REFERENCE.fullmatch(candidate)
    if direct:
        return _dependency(direct.group("name"), f"@ {direct.group('url')}", source_path, candidate)
    match = _REQUIREMENT.fullmatch(candidate)
    if not match:
        return None
    constraint = (match.group("constraints") or "").replace(" ", "") or None
    if match.group("extras"):
        constraint = f"[{match.group('extras')}]{constraint or ''}"
    if match.group("marker"):
        constraint = f"{constraint or ''}; {match.group('marker').strip()}"
    return _dependency(match.group("name"), constraint, source_path, candidate)


def parse_requirements_txt(content: str, source_path: str) -> list[EnvironmentDependency]:
    return [
        dependency
        for line in content.splitlines()
        if (dependency := parse_requirement_line(line, source_path)) is not None
    ]


def _parse_conda_dependency(value: str, source_path: str) -> EnvironmentDependency | None:
    if any(operator in value for operator in ("==", ">", "<", "~", "!")):
        return parse_requirement_line(value, source_path)
    match = re.fullmatch(rf"(?P<name>{_NAME})(?:=(?P<version>[^\s]+))?", value)
    if not match:
        return None
    version = match.group("version")
    if version:
        version = version.split("=")[0]
    return _dependency(match.group("name"), f"=={version}" if version else None, source_path, value)


def parse_environment_yml(content: str, source_path: str) -> list[EnvironmentDependency]:
    dependencies: list[EnvironmentDependency] = []
    in_dependencies = False
    dependency_indent = 0
    pip_indent: int | None = None
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        if stripped == "dependencies:":
            in_dependencies = True
            dependency_indent = indent
            pip_indent = None
            continue
        if not in_dependencies:
            continue
        if indent <= dependency_indent:
            in_dependencies = False
            pip_indent = None
            continue
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if value == "pip:":
            pip_indent = indent
            continue
        if pip_indent is not None and indent > pip_indent:
            dependency = parse_requirement_line(value, source_path)
        else:
            pip_indent = None
            dependency = _parse_conda_dependency(value, source_path)
        if dependency is not None:
            dependencies.append(dependency)
    return dependencies


def _toml_dependency(name: str, value: object, source_path: str, section: str) -> EnvironmentDependency | None:
    if isinstance(value, str):
        constraint = value
    elif isinstance(value, dict) and isinstance(value.get("version"), str):
        constraint = value["version"]
    else:
        return None
    return _dependency(
        name,
        None if constraint == "*" else constraint,
        source_path,
        f"{section}: {name} = {constraint}",
    )


def parse_pyproject_toml_with_diagnostics(
    content: str, source_path: str
) -> tuple[list[EnvironmentDependency], list[str]]:
    dependencies: list[EnvironmentDependency] = []
    diagnostics: list[str] = []
    try:
        document = tomllib.loads(content)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        return [], [f"Could not parse {source_path}: {type(exc).__name__}."]

    project = document.get("project")
    if isinstance(project, dict):
        requires_python = project.get("requires-python")
        if isinstance(requires_python, str):
            dependencies.append(_dependency(
                "python", requires_python, source_path,
                f"project.requires-python = {requires_python}",
            ))
        if isinstance(project.get("dependencies"), list):
            for value in project["dependencies"]:
                dependency = parse_requirement_line(value, source_path) if isinstance(value, str) else None
                if dependency is not None:
                    dependencies.append(dependency)
                else:
                    diagnostics.append(f"Ignored malformed dependency in {source_path}.")

    poetry = document.get("tool", {}).get("poetry", {})
    if isinstance(poetry, dict):
        sections = [
            ("tool.poetry.dependencies", poetry.get("dependencies")),
            ("tool.poetry.dev-dependencies", poetry.get("dev-dependencies")),
        ]
        groups = poetry.get("group")
        if isinstance(groups, dict):
            for group_name, group in groups.items():
                if isinstance(group, dict):
                    sections.append((f"tool.poetry.group.{group_name}.dependencies", group.get("dependencies")))
        for section, values in sections:
            if not isinstance(values, dict):
                continue
            for name, value in values.items():
                dependency = _toml_dependency(str(name), value, source_path, section)
                if dependency is not None:
                    dependencies.append(dependency)
                else:
                    diagnostics.append(f"Ignored unsupported {section} entry for {name}.")

    build_requires = document.get("build-system", {}).get("requires")
    if isinstance(build_requires, list):
        for value in build_requires:
            dependency = parse_requirement_line(value, source_path) if isinstance(value, str) else None
            if dependency is not None:
                dependencies.append(dependency.model_copy(update={"dependency_type": DependencyType.TOOL}))
    return dependencies, diagnostics


def parse_pyproject_toml(content: str, source_path: str) -> list[EnvironmentDependency]:
    return parse_pyproject_toml_with_diagnostics(content, source_path)[0]


def parse_pipfile(content: str, source_path: str) -> tuple[list[EnvironmentDependency], list[str]]:
    try:
        document = tomllib.loads(content)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        return [], [f"Could not parse {source_path}: {type(exc).__name__}."]
    dependencies: list[EnvironmentDependency] = []
    requires = document.get("requires", {})
    if isinstance(requires, dict):
        python = requires.get("python_version") or requires.get("python_full_version")
        if isinstance(python, str):
            dependencies.append(_dependency("python", f"=={python}", source_path, f"requires.python = {python}"))
    for section in ("packages", "dev-packages"):
        values = document.get(section)
        if not isinstance(values, dict):
            continue
        for name, value in values.items():
            dependency = _toml_dependency(str(name), value, source_path, section)
            if dependency is not None:
                dependencies.append(dependency)
    return dependencies, []


def parse_lock_file(content: str, source_path: str) -> tuple[list[EnvironmentDependency], list[str]]:
    """Parse Pipfile.lock JSON or Poetry lock TOML without executing lock tooling."""

    if source_path.casefold().endswith("pipfile.lock"):
        try:
            document = json.loads(content)
        except (json.JSONDecodeError, ValueError) as exc:
            return [], [f"Could not parse {source_path}: {type(exc).__name__}."]
        dependencies: list[EnvironmentDependency] = []
        for section in ("default", "develop"):
            values = document.get(section)
            if not isinstance(values, dict):
                continue
            for name, value in values.items():
                constraint = value.get("version") if isinstance(value, dict) else value
                if isinstance(constraint, str):
                    dependencies.append(_dependency(str(name), constraint, source_path, f"{section}: {name} = {constraint}"))
        return dependencies, []
    try:
        document = tomllib.loads(content)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        return [], [f"Could not parse {source_path}: {type(exc).__name__}."]
    dependencies = []
    for package in document.get("package", []):
        if isinstance(package, dict) and isinstance(package.get("name"), str):
            version = package.get("version")
            dependencies.append(_dependency(
                package["name"], f"=={version}" if isinstance(version, str) else None,
                source_path, f"package: {package['name']} {version or ''}".strip(),
            ))
    return dependencies, []


def parse_setup_cfg(content: str, source_path: str) -> tuple[list[EnvironmentDependency], list[str]]:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(content)
    except configparser.Error as exc:
        return [], [f"Could not parse {source_path}: {type(exc).__name__}."]
    dependencies: list[EnvironmentDependency] = []
    if parser.has_option("options", "python_requires"):
        value = parser.get("options", "python_requires").strip()
        dependencies.append(_dependency("python", value, source_path, f"python_requires = {value}"))
    if parser.has_option("options", "install_requires"):
        dependencies.extend(parse_requirements_txt(parser.get("options", "install_requires"), source_path))
    return dependencies, []


def _logical_lines(content: str) -> list[str]:
    lines: list[str] = []
    current = ""
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        current = f"{current} {stripped}".strip()
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        lines.append(current)
        current = ""
    if current:
        lines.append(current)
    return lines


def _installed_packages(command: str) -> list[str]:
    match = re.search(
        r"\b(?:apt-get|apt|yum|dnf)\s+install\b(?P<body>.*)|\bapk\s+add\b(?P<apk>.*)",
        command,
        re.IGNORECASE,
    )
    if not match:
        return []
    body = match.group("body") or match.group("apk") or ""
    try:
        tokens = shlex.split(body, posix=True)
    except ValueError:
        tokens = body.split()
    packages: list[str] = []
    for token in tokens:
        if token in {"&&", ";", "|"}:
            break
        if token.startswith(("-", "$")):
            continue
        name = token.split("=", 1)[0].strip()
        if re.fullmatch(_NAME, name):
            packages.append(name)
    return list(dict.fromkeys(packages))


def extract_env_vars(content: str) -> list[str]:
    names: list[str] = []
    for line in _logical_lines(content):
        export = re.match(r"export\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if export:
            names.append(export.group(1))
            continue
        instruction = re.match(r"(?:ENV|ARG)\s+(.+)$", line, re.IGNORECASE)
        if instruction:
            for match in re.finditer(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|\s)", instruction.group(1)):
                names.append(match.group(1))
            continue
        assignment = re.fullmatch(r"([A-Z_][A-Z0-9_]*)\s*=.*", line)
        if assignment:
            names.append(assignment.group(1))
    return list(dict.fromkeys(names))


def parse_dockerfile(content: str, source_path: str) -> DockerfileData:
    base_image = os_name = os_version = python_version = cuda_version = cudnn_version = working_directory = None
    system_dependencies: list[str] = []
    commands: list[str] = []
    evidence: list[EnvironmentEvidence] = []
    for line in _logical_lines(content):
        from_match = re.match(r"FROM\s+(?:--platform=\S+\s+)?([^\s]+)", line, re.IGNORECASE)
        if from_match:
            base_image = from_match.group(1)
            evidence.append(EnvironmentEvidence(
                category="container", value=base_image, source_path=source_path,
                evidence=f"FROM {base_image}", certainty=Certainty.EXPLICIT,
            ))
            lower = base_image.casefold()
            for candidate in ("ubuntu", "debian", "alpine", "centos", "rockylinux"):
                match = re.search(rf"{candidate}(?::|-)?([0-9.]+)?", lower)
                if match:
                    os_name, os_version = candidate.capitalize(), match.group(1) or None
                    break
            python_match = re.search(r"python(?::|-)(\d+(?:\.\d+){1,2})", lower)
            cuda_match = re.search(r"(?:nvidia/)?cuda(?::|-)(\d+(?:\.\d+){1,2})", lower)
            cudnn_match = re.search(r"(?:^|[-_:])cudnn(\d+(?:\.\d+)*)?(?:[-_:]|$)", lower)
            python_version = python_match.group(1) if python_match else None
            cuda_version = cuda_match.group(1) if cuda_match else None
            cudnn_version = cudnn_match.group(1) if cudnn_match and cudnn_match.group(1) else None
        if line.upper().startswith("RUN "):
            packages = _installed_packages(line[4:])
            system_dependencies.extend(packages)
            evidence.extend(EnvironmentEvidence(
                category="system_dependency", value=package, source_path=source_path,
                evidence="Documented container package installation", certainty=Certainty.EXPLICIT,
            ) for package in packages)
        if line.upper().startswith(("CMD ", "ENTRYPOINT ")):
            commands.append(line)
        if line.upper().startswith("WORKDIR "):
            working_directory = line.split(None, 1)[1].strip()
    return DockerfileData(
        base_image=base_image,
        operating_system=os_name,
        operating_system_version=os_version,
        python_version=python_version,
        cuda_version=cuda_version,
        cudnn_version=cudnn_version,
        system_dependencies=list(dict.fromkeys(system_dependencies)),
        environment_variables=extract_env_vars(content),
        commands=list(dict.fromkeys(commands)),
        working_directory=working_directory,
        evidence=evidence,
    )


def parse_dockerfile_system_deps(content: str) -> list[str]:
    return parse_dockerfile(content, "Dockerfile").system_dependencies


def parse_documentation(content: str, source_path: str) -> DocumentationData:
    evidence: list[EnvironmentEvidence] = []
    commands: list[str] = []
    system_dependencies: list[str] = []
    patterns = {
        "python": r"\bPython\s*(?:version\s*)?(?:==|>=|<=|~=|>|<|is|:)?\s*v?(\d+(?:\.\d+){1,2})",
        "cuda": r"\bCUDA\s*(?:version\s*)?(?:==|>=|<=|is|:)?\s*v?(\d+(?:\.\d+){1,2})",
        "cudnn": r"\bcuDNN\s*(?:version\s*)?(?:==|>=|<=|is|:)?\s*v?(\d+(?:\.\d+){0,2})",
        "storage": r"\b(\d+(?:\.\d+)?\s*(?:GB|GiB|TB|TiB))\s+(?:of\s+)?(?:disk|storage)",
    }
    for raw_line in content.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        for category, pattern in patterns.items():
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                evidence.append(EnvironmentEvidence(
                    category=category, value=match.group(1), source_path=source_path,
                    evidence=line[:300], certainty=Certainty.EXPLICIT,
                ))
        gpu_memory_match = re.search(
            r"\b(\d+(?:\.\d+)?\s*(?:GB|GiB))\s*(?:of\s+)?(?:GPU|VRAM)\b",
            line,
            re.IGNORECASE,
        ) or re.search(
            r"\b(?:GPU|VRAM)\b[^.]{0,40}?\b(\d+(?:\.\d+)?\s*(?:GB|GiB))\b",
            line,
            re.IGNORECASE,
        ) or re.search(
            r"\b(\d+(?:\.\d+)?\s*(?:GB|GiB))\s+(?:of\s+)?device\s+RAM\b",
            line,
            re.IGNORECASE,
        )
        if gpu_memory_match:
            evidence.append(EnvironmentEvidence(
                category="gpu_memory", value=gpu_memory_match.group(1),
                source_path=source_path, evidence=line[:300], certainty=Certainty.EXPLICIT,
            ))
        memory_match = re.search(
            r"\b(\d+(?:\.\d+)?\s*(?:GB|GiB))\s+(?:of\s+)?(?:system\s+)?(?:RAM|memory)\b",
            line,
            re.IGNORECASE,
        )
        if memory_match and not re.search(
            r"\b(?:GPU|VRAM|device\s+RAM)\b", line, re.IGNORECASE
        ):
            evidence.append(EnvironmentEvidence(
                category="memory", value=memory_match.group(1), source_path=source_path,
                evidence=line[:300], certainty=Certainty.EXPLICIT,
            ))
        os_match = re.search(r"\b(Ubuntu|Debian|Alpine|CentOS|Rocky Linux|Windows|macOS)\s*(\d+(?:\.\d+)*)?", line, re.IGNORECASE)
        if os_match:
            evidence.append(EnvironmentEvidence(
                category="operating_system", value=os_match.group(1), source_path=source_path,
                evidence=line[:300], certainty=Certainty.EXPLICIT,
            ))
            if os_match.group(2):
                evidence.append(EnvironmentEvidence(
                    category="operating_system_version", value=os_match.group(2), source_path=source_path,
                    evidence=line[:300], certainty=Certainty.EXPLICIT,
                ))
        gpu_match = re.search(r"\b((?:NVIDIA\s+)?(?:A100|V100|H100|T4|RTX\s*\d{3,4}|GPU))\b", line, re.IGNORECASE)
        if gpu_match and re.search(r"\b(require|required|requires|recommended|using|trained on)\b", line, re.IGNORECASE):
            evidence.append(EnvironmentEvidence(
                category="gpu", value=gpu_match.group(1), source_path=source_path,
                evidence=line[:300], certainty=Certainty.EXPLICIT,
            ))
        gpu_config = re.search(r"\b(?:gpus?|accelerator)\s*[:=]\s*(gpu|cuda|[1-9]\d*)\b", line, re.IGNORECASE)
        if gpu_config:
            evidence.append(EnvironmentEvidence(
                category="gpu", value=f"GPU configuration: {gpu_config.group(1)}",
                source_path=source_path, evidence=line[:300], certainty=Certainty.EXPLICIT,
            ))
        cpu_match = re.search(r"\b(\d+[- ]?(?:core|CPU cores?))\b", line, re.IGNORECASE)
        if cpu_match:
            evidence.append(EnvironmentEvidence(
                category="cpu", value=cpu_match.group(1), source_path=source_path,
                evidence=line[:300], certainty=Certainty.EXPLICIT,
            ))
        packages = _installed_packages(line)
        system_dependencies.extend(packages)
        evidence.extend(EnvironmentEvidence(
            category="system_dependency", value=package, source_path=source_path,
            evidence=line[:300], certainty=Certainty.EXPLICIT,
        ) for package in packages)
        clean_line = line.strip("`'\" ")
        if (
            clean_line.startswith("$") or re.match(r"(?:python|conda|pip|poetry|make)\s+", clean_line, re.IGNORECASE)
        ) and "=" not in clean_line and not re.search(r"KEY|TOKEN|SECRET|PASSWORD|PASS|PWD|AUTH", clean_line, re.IGNORECASE):
            commands.append(clean_line.lstrip("$ "))
    return DocumentationData(
        evidence=evidence,
        environment_variables=extract_env_vars(content),
        commands=list(dict.fromkeys(commands)),
        system_dependencies=list(dict.fromkeys(system_dependencies)),
    )
