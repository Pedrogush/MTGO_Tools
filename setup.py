from pathlib import Path

import setuptools


def load_requirements(filename: str) -> list[str]:
    requirements = []
    for line in Path(__file__).with_name(filename).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        requirements.append(stripped)
    return requirements


setuptools.setup(
    name="mtg_metagame_tools",
    version="0.2",
    author="yochi",
    author_email="pedrogush@gmail.com",
    description="MTG Metagame Analysis: Opponent tracking and deck research tools for MTGO",
    # Discover every application package (including PEP 420 namespace packages such as
    # ``widgets``, ``utils`` and ``navigators`` which intentionally omit ``__init__.py``)
    # so that ``pip install .`` and wheel builds ship the full runtime, not just the
    # three top-level packages that used to be listed explicitly.
    packages=setuptools.find_namespace_packages(
        include=[
            "automation*",
            "controllers*",
            "navigators*",
            "repositories*",
            "services*",
            "utils*",
            "widgets*",
        ],
        exclude=[
            "tests",
            "tests.*",
            "*.tests",
            "*.tests.*",
            "build*",
            "dist*",
            "env*",
            "venv*",
        ],
    ),
    include_package_data=True,
    classifiers=["Programming Language :: Python :: 3", "Operating System :: Windows"],
    python_requires=">=3.11",
    install_requires=load_requirements("requirements.txt"),
)
