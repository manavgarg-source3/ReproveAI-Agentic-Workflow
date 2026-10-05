import re
from typing import Iterator

from app.schemas.research import (
    Certainty,
    DependencyType,
    EnvironmentDependency,
)

def parse_requirements_txt(content: str, source_path: str) -> list[EnvironmentDependency]:
    """Parse python packages from a requirements.txt file."""
    dependencies = []
    
    # Basic regex to match common pip requirements formats: package==version, package>=version, package
    req_pattern = re.compile(r"^([a-zA-Z0-9_\-]+)(.*?)(?:\s+#.*)?$")
    
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-") or line.startswith("http") or line.startswith("git+"):
            continue
            
        match = req_pattern.match(line)
        if match:
            name = match.group(1).strip()
            constraint = match.group(2).strip() or None
            
            # Simple handling of exact pip freeze output if needed, but constraint usually has ==
            dependencies.append(EnvironmentDependency(
                name=name,
                version_constraint=constraint,
                dependency_type=DependencyType.PYTHON_PACKAGE,
                source_path=source_path,
                evidence=line,
                certainty=Certainty.EXPLICIT,
            ))
            
    return dependencies

def parse_environment_yml(content: str, source_path: str) -> list[EnvironmentDependency]:
    """Extract dependencies from environment.yml. Uses basic string parsing to avoid PyYAML dependency in parser."""
    dependencies = []
    
    in_dependencies = False
    in_pip = False
    
    for line in content.splitlines():
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("#"):
            continue
            
        if line_stripped == "dependencies:":
            in_dependencies = True
            in_pip = False
            continue
            
        if in_dependencies:
            if not line.startswith(" ") and not line.startswith("\t"):
                # Exited dependencies block
                in_dependencies = False
                in_pip = False
                continue
                
            if line_stripped.startswith("- "):
                dep_str = line_stripped[2:].strip()
                # Skip pip: sub-block start
                if dep_str == "pip:":
                    in_pip = True
                    continue
                    
                if in_pip:
                    # Dependencies under pip: are parsed as normal requirements
                    if "==" in dep_str:
                        parts = dep_str.split("==", 1)
                        name = parts[0].strip()
                        constraint = "==" + parts[1].strip()
                    elif ">=" in dep_str:
                        parts = dep_str.split(">=", 1)
                        name = parts[0].strip()
                        constraint = ">=" + parts[1].strip()
                    elif ">" in dep_str or "<" in dep_str:
                        match = re.match(r"^([a-zA-Z0-9_\-]+)(.*)$", dep_str)
                        if match:
                            name = match.group(1).strip()
                            constraint = match.group(2).strip()
                        else:
                            continue
                    else:
                        name = dep_str
                        constraint = None
                else:
                    # Conda dependencies format (e.g. python=3.8 or pytorch>=1.8)
                    if ">=" in dep_str:
                        parts = dep_str.split(">=", 1)
                        name = parts[0].strip()
                        constraint = ">=" + parts[1].strip()
                    elif "<=" in dep_str:
                        parts = dep_str.split("<=", 1)
                        name = parts[0].strip()
                        constraint = "<=" + parts[1].strip()
                    elif "=" in dep_str:
                        parts = dep_str.split("=", 1)
                        name = parts[0].strip()
                        constraint = "==" + parts[1].strip() if not parts[1].strip().startswith(("=", ">", "<")) else parts[1].strip()
                    elif ">" in dep_str or "<" in dep_str:
                        match = re.match(r"^([a-zA-Z0-9_\-]+)(.*)$", dep_str)
                        if match:
                            name = match.group(1).strip()
                            constraint = match.group(2).strip()
                        else:
                            continue
                    else:
                        name = dep_str
                        constraint = None
                    
                dependencies.append(EnvironmentDependency(
                    name=name,
                    version_constraint=constraint,
                    dependency_type=DependencyType.PYTHON_PACKAGE,
                    source_path=source_path,
                    evidence=line_stripped,
                    certainty=Certainty.EXPLICIT,
                ))
    
    return dependencies

def parse_pyproject_toml(content: str, source_path: str) -> list[EnvironmentDependency]:
    """Basic extraction of dependencies from pyproject.toml without toml library."""
    dependencies = []
    
    in_dependencies = False
    in_poetry_deps = False
    
    for line in content.splitlines():
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("#"):
            continue
            
        if line_stripped.startswith("[") and line_stripped.endswith("]"):
            in_dependencies = line_stripped == "[project.dependencies]"
            in_poetry_deps = line_stripped == "[tool.poetry.dependencies]"
            continue
            
        if in_dependencies:
            # project.dependencies is a list of strings
            pass # Skipping for now without proper parser, or handle simple cases
            
        if in_poetry_deps:
            # format: package = "version"
            if "=" in line_stripped:
                parts = line_stripped.split("=", 1)
                name = parts[0].strip().strip('"').strip("'")
                # version can be an object or a string
                constraint_str = parts[1].strip()
                if constraint_str.startswith("{"):
                    # Complex constraint, ignore for now
                    continue
                else:
                    constraint = constraint_str.strip('"').strip("'")
                    
                dependencies.append(EnvironmentDependency(
                    name=name,
                    version_constraint=constraint,
                    dependency_type=DependencyType.PYTHON_PACKAGE,
                    source_path=source_path,
                    evidence=line_stripped,
                    certainty=Certainty.EXPLICIT,
                ))
                
    return dependencies

def parse_dockerfile_system_deps(content: str) -> list[str]:
    """Extract system dependencies from Dockerfile."""
    deps = []
    
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
            
        if line.startswith("RUN "):
            if "apt-get install" in line or "apt install" in line or "yum install" in line or "apk add" in line:
                # Basic heuristic extraction
                parts = line.split()
                in_install = False
                for p in parts:
                    if p in ("install", "add"):
                        in_install = True
                        continue
                    if in_install and not p.startswith("-") and p not in ("&&", "\\"):
                        deps.append(p)
                            
    return list(set(deps))

def extract_env_vars(content: str) -> list[str]:
    """Extract environment variable names assigned in documentation."""
    vars_found = []
    
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("export ") and "=" in line:
            var_name = line[len("export "):].split("=")[0].strip()
            vars_found.append(var_name)
        elif line.startswith("ENV ") and " " in line:
            # Dockerfile format
            parts = line[4:].strip().split()
            if "=" in parts[0]:
                vars_found.append(parts[0].split("=")[0])
            else:
                vars_found.append(parts[0])
                
    return list(set(vars_found))

