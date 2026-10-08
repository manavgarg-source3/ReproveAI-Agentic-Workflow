"""Deterministic Step 4 parser coverage."""

import pytest

from app.services.environment.parsers import (
    extract_env_vars,
    is_secret_variable,
    parse_dockerfile,
    parse_documentation,
    parse_environment_yml,
    parse_pipfile,
    parse_pyproject_toml_with_diagnostics,
    parse_requirements_txt,
    parse_setup_cfg,
)


def test_requirements_supports_common_constraints_and_rejects_malformed_lines() -> None:
    dependencies = parse_requirements_txt(
        """
        torch==2.0.1
        numpy>=1.24
        transformers
        package~=1.2
        requests[security]>=2.31; python_version < "3.12"
        bad line !!!
        -r base.txt
        """,
        "requirements.txt",
    )

    assert [item.name for item in dependencies] == [
        "torch", "numpy", "transformers", "package", "requests"
    ]
    assert dependencies[3].version_constraint == "~=1.2"
    assert dependencies[4].source_path == "requirements.txt"
    assert all(item.certainty.value == "EXPLICIT" for item in dependencies)


def test_conda_and_nested_pip_dependencies_are_parsed() -> None:
    dependencies = parse_environment_yml(
        """
        channels:
          - conda-forge
        dependencies:
          - python=3.10
          - pytorch>=2.1
          - pip:
            - transformers~=4.40
            - numpy<=1.26
        """,
        "environment.yaml",
    )

    assert [(item.name, item.version_constraint) for item in dependencies] == [
        ("python", "==3.10"),
        ("pytorch", ">=2.1"),
        ("transformers", "~=4.40"),
        ("numpy", "<=1.26"),
    ]


def test_pep621_poetry_groups_and_build_requirements_are_parsed() -> None:
    dependencies, diagnostics = parse_pyproject_toml_with_diagnostics(
        """
        [project]
        requires-python = ">=3.10"
        dependencies = ["requests>=2.31", "numpy==1.26"]

        [tool.poetry.dependencies]
        python = "^3.10"
        torch = {version = "^2.1", extras = ["cuda"]}

        [tool.poetry.group.dev.dependencies]
        pytest = "^8"

        [build-system]
        requires = ["setuptools>=68"]
        """,
        "pyproject.toml",
    )

    assert diagnostics == []
    assert {item.name for item in dependencies} == {
        "python", "requests", "numpy", "torch", "pytest", "setuptools"
    }
    assert next(item for item in dependencies if item.name == "torch").version_constraint == "^2.1"


def test_malformed_toml_returns_diagnostic_without_crashing() -> None:
    dependencies, diagnostics = parse_pyproject_toml_with_diagnostics(
        "[project\ndependencies = [", "pyproject.toml"
    )

    assert dependencies == []
    assert diagnostics == ["Could not parse pyproject.toml: TOMLDecodeError."]


def test_pipfile_and_setup_cfg_extract_python_and_dependencies() -> None:
    pip_dependencies, pip_diagnostics = parse_pipfile(
        """
        [requires]
        python_version = "3.11"
        [packages]
        flask = "==3.0"
        """,
        "Pipfile",
    )
    setup_dependencies, setup_diagnostics = parse_setup_cfg(
        """
        [options]
        python_requires = >=3.9
        install_requires =
            requests>=2
            numpy
        """,
        "setup.cfg",
    )

    assert pip_diagnostics == setup_diagnostics == []
    assert [(item.name, item.version_constraint) for item in pip_dependencies] == [
        ("python", "==3.11"), ("flask", "==3.0")
    ]
    assert {item.name for item in setup_dependencies} == {"python", "requests", "numpy"}


def test_dockerfile_extracts_bounded_environment_metadata() -> None:
    result = parse_dockerfile(
        """
        FROM nvidia/cuda:12.1-runtime-ubuntu22.04
        ARG BUILD_TOKEN=ignored
        ENV API_KEY=ignored CUDA_VISIBLE_DEVICES=0
        RUN apt-get update && apt-get install -y git \\
            build-essential cmake
        WORKDIR /workspace
        CMD ["python", "train.py"]
        """,
        "Dockerfile",
    )

    assert result.base_image == "nvidia/cuda:12.1-runtime-ubuntu22.04"
    assert result.operating_system == "Ubuntu"
    assert result.operating_system_version == "22.04"
    assert result.cuda_version == "12.1"
    assert result.system_dependencies == ["git", "build-essential", "cmake"]
    assert result.environment_variables == ["BUILD_TOKEN", "API_KEY", "CUDA_VISIBLE_DEVICES"]
    assert result.commands == ['CMD ["python", "train.py"]']


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04", "8"),
        ("nvidia/cuda:12.1.0-cudnn8.6-runtime-ubuntu22.04", "8.6"),
        ("nvidia/cuda:12.1.0-runtime-ubuntu22.04", None),
        ("nvidia/cuda:12.1.0-cudnnbad-runtime-ubuntu22.04", None),
    ],
)
def test_dockerfile_extracts_only_explicit_valid_cudnn_tags(image: str, expected: str | None) -> None:
    result = parse_dockerfile(f"FROM {image}", "Dockerfile")

    assert result.cudnn_version == expected


def test_documentation_extracts_explicit_hardware_commands_and_system_packages() -> None:
    result = parse_documentation(
        """
        Requires Python 3.10, CUDA 12.1, cuDNN 9, and an NVIDIA V100 GPU.
        Use 16 GB of RAM and 50 GB of storage.
        sudo apt-get install -y libsndfile1 ffmpeg
        python train.py --config config.yaml
        export DATABASE_PASSWORD=never-return-this
        """,
        "README.md",
    )

    categories = {item.category for item in result.evidence}
    assert {"python", "cuda", "cudnn", "gpu", "memory", "storage"} <= categories
    assert result.system_dependencies == ["libsndfile1", "ffmpeg"]
    assert result.commands == ["python train.py --config config.yaml"]
    assert result.environment_variables == ["DATABASE_PASSWORD"]
    assert "never-return-this" not in repr(result)


def test_documentation_extracts_inline_commands_and_dependency_bullets() -> None:
    result = parse_documentation(
        """
        Basic usage
        --------
        * Ideal mass-spring: `python3 experiment-spring/train.py --verbose`

        Dependencies
        --------
        * OpenAI Gym
        * PyTorch
        * NumPy
        * ImageIO
        * Scipy

        This project is written in Python 3.
        """,
        "README.md",
    )

    assert result.commands == ["python3 experiment-spring/train.py --verbose"]
    assert {item.name for item in result.dependencies} == {
        "gym", "torch", "numpy", "imageio", "scipy"
    }
    assert ("python", "3") in {
        (item.category, item.value) for item in result.evidence
    }


def test_documentation_distinguishes_gpu_memory_from_system_memory() -> None:
    result = parse_documentation(
        "Requires an NVIDIA V100 16GB GPU.\nRequires 64 GB of system RAM.",
        "README.md",
    )

    values = {(item.category, item.value) for item in result.evidence}
    assert ("gpu_memory", "16GB") in values
    assert ("memory", "64 GB") in values
    assert ("memory", "16GB") not in values


def test_secret_classification_covers_password_auth_and_non_secret_variables() -> None:
    secret_names = [
        "API_KEY", "GEMINI_API_KEY", "TOKEN", "CLIENT_SECRET", "DATABASE_PASSWORD",
        "DB_PASS", "PWD", "CREDENTIAL", "AUTH_TOKEN", "PRIVATE_KEY",
    ]

    assert all(is_secret_variable(name) for name in secret_names)
    assert not is_secret_variable("CUDA_VISIBLE_DEVICES")
    assert extract_env_vars("export API_KEY=abc\nexport CUDA_VISIBLE_DEVICES=0") == [
        "API_KEY", "CUDA_VISIBLE_DEVICES"
    ]


def test_bare_environment_assignments_retain_names_only_and_reject_prose() -> None:
    content = """API_KEY=abc123
DATABASE_PASSWORD=supersecret
TOKEN=secret123
NORMAL_SETTING=value
This value = something
"""

    names = extract_env_vars(content)

    assert names == ["API_KEY", "DATABASE_PASSWORD", "TOKEN", "NORMAL_SETTING"]
    assert all(is_secret_variable(name) for name in names[:3])
    assert not is_secret_variable(names[3])
    assert not {"abc123", "supersecret", "secret123"} & set(names)
