from app.services.environment.parsers import (
    parse_requirements_txt,
    parse_environment_yml,
    parse_pyproject_toml,
    parse_dockerfile_system_deps,
    extract_env_vars,
)
from app.schemas.research import (
    Certainty,
    DependencyType,
    EnvironmentDependency,
)

def test_parse_requirements_txt():
    content = """
    # comment
    torch==1.9.0
    numpy>=1.18.0
    requests
    """
    deps = parse_requirements_txt(content, "requirements.txt")
    assert len(deps) == 3
    assert deps[0].name == "torch"
    assert deps[0].version_constraint == "==1.9.0"
    assert deps[0].certainty == Certainty.EXPLICIT
    
    assert deps[1].name == "numpy"
    assert deps[1].version_constraint == ">=1.18.0"
    
    assert deps[2].name == "requests"
    assert deps[2].version_constraint is None

def test_parse_environment_yml():
    content = """
    name: test-env
    dependencies:
      - python=3.8
      - pytorch>=1.8
      - scipy
      - pip:
        - something==1.0
    """
    deps = parse_environment_yml(content, "environment.yml")
    assert len(deps) == 4
    assert deps[0].name == "python"
    assert deps[0].version_constraint == "==3.8"
    assert deps[1].name == "pytorch"
    assert deps[1].version_constraint == ">=1.8"
    assert deps[2].name == "scipy"
    assert deps[2].version_constraint is None
    assert deps[3].name == "something"
    assert deps[3].version_constraint == "==1.0"

def test_parse_pyproject_toml():
    content = """
    [tool.poetry.dependencies]
    python = "^3.8"
    tensorflow = "2.5.0"
    requests = {version = "^2.25", extras = ["security"]}
    """
    deps = parse_pyproject_toml(content, "pyproject.toml")
    assert len(deps) == 2  # ignoring complex object requirement for now
    assert deps[0].name == "python"
    assert deps[0].version_constraint == "^3.8"
    assert deps[1].name == "tensorflow"
    assert deps[1].version_constraint == "2.5.0"

def test_parse_dockerfile():
    content = """
    FROM ubuntu:20.04
    RUN apt-get update && apt-get install -y git build-essential cmake
    ENV MODEL_DIR=/models
    """
    system_deps = parse_dockerfile_system_deps(content)
    assert "git" in system_deps
    assert "build-essential" in system_deps
    assert "cmake" in system_deps
    assert "update" not in system_deps
    
    env_vars = extract_env_vars(content)
    assert "MODEL_DIR" in env_vars

def test_extract_env_vars_from_readme():
    content = """
    To run this, you need to set some variables:
    export HF_TOKEN=your_token_here
    export DATA_DIR=/path/to/data
    """
    env_vars = extract_env_vars(content)
    assert "HF_TOKEN" in env_vars
    assert "DATA_DIR" in env_vars
