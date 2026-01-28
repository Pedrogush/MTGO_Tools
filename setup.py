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
    packages=["widgets", "navigators", "utils"],
    classifiers=["Programming Language :: Python :: 3", "Operating System :: Windows"],
    python_requires=">=3.11",
    install_requires=load_requirements("requirements.txt"),
)
