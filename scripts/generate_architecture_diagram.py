#!/usr/bin/env python3
import ast
from collections import defaultdict
from pathlib import Path


class ArchitectureAnalyzer(ast.NodeVisitor):
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.classes = []
        self.imports = []

    def visit_ClassDef(self, node):
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(alias.name)

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.append(node.module)


def analyze_directory(directory: Path) -> dict[str, dict]:
    modules = {}
    for py_file in directory.rglob("*.py"):
        if "__pycache__" in str(py_file) or "test" in str(py_file):
            continue

        try:
            with open(py_file, encoding="utf-8") as f:
                tree = ast.parse(f.read())

            rel_path = py_file.relative_to(directory.parent)
            module_name = str(rel_path).replace("/", ".").replace(".py", "")

            analyzer = ArchitectureAnalyzer(module_name)
            analyzer.visit(tree)

            modules[module_name] = {
                "classes": analyzer.classes,
                "imports": analyzer.imports,
                "path": str(rel_path),
            }
        except Exception:
            pass

    return modules


def categorize_modules(modules: dict) -> dict[str, list[str]]:
    categories = {
        "Controllers": [],
        "Services": [],
        "Repositories": [],
        "UI": [],
        "Utils": [],
        "Navigators": [],
    }

    for module_name in modules.keys():
        if "controller" in module_name:
            categories["Controllers"].append(module_name)
        elif "service" in module_name:
            categories["Services"].append(module_name)
        elif "repositor" in module_name:
            categories["Repositories"].append(module_name)
        elif "widget" in module_name or "frame" in module_name or "panel" in module_name:
            categories["UI"].append(module_name)
        elif "navigator" in module_name:
            categories["Navigators"].append(module_name)
        elif "utils" in module_name or "util" in module_name:
            categories["Utils"].append(module_name)

    return {k: v for k, v in categories.items() if v}


def find_dependencies(modules: dict) -> dict[str, set[str]]:
    deps = defaultdict(set)
    for module_name, module_info in modules.items():
        for imp in module_info["imports"]:
            for other_module in modules.keys():
                if other_module != module_name and other_module in imp:
                    deps[module_name].add(other_module)
    return deps


def generate_mermaid(categories: dict, dependencies: dict, modules: dict) -> str:
    lines = ["graph TB"]

    key_modules = {
        "Controllers": "app_controller",
        "Services": ["deck_service", "collection_service", "search_service", "mtgo_bridge_service"],
        "Repositories": ["card_repository", "deck_repository", "metagame_repository"],
        "UI": ["app_frame", "deck_builder_panel", "card_table_panel"],
        "Utils": ["deck", "atomic_io", "card_images"],
        "Navigators": ["mtggoldfish"],
    }

    for category, patterns in key_modules.items():
        if isinstance(patterns, str):
            patterns = [patterns]

        lines.append(f"\n    subgraph {category}")
        count = 0
        for module_name, module_info in modules.items():
            if count >= 3:
                break
            if any(pattern in module_name for pattern in patterns):
                module_id = module_name.replace(".", "_")
                label = module_name.split(".")[-1]
                classes = module_info.get("classes", [])
                if classes:
                    class_list = ", ".join(classes[:2])
                    lines.append(f'        {module_id}["{label}<br/>{class_list}"]')
                else:
                    lines.append(f'        {module_id}["{label}"]')
                count += 1
        lines.append("    end")

    lines.append("\n    %% Key Dependencies")
    layer_deps = [
        ("Controllers", "Services"),
        ("Controllers", "UI"),
        ("Services", "Repositories"),
        ("Services", "Utils"),
        ("Repositories", "Utils"),
        ("Repositories", "Navigators"),
    ]

    for source_cat, target_cat in layer_deps:
        source_patterns = key_modules.get(source_cat, [])
        target_patterns = key_modules.get(target_cat, [])

        if isinstance(source_patterns, str):
            source_patterns = [source_patterns]
        if isinstance(target_patterns, str):
            target_patterns = [target_patterns]

        source_modules = [
            m.replace(".", "_") for m in modules.keys() if any(p in m for p in source_patterns)
        ][:1]
        target_modules = [
            m.replace(".", "_") for m in modules.keys() if any(p in m for p in target_patterns)
        ][:1]
        if source_modules and target_modules:
            lines.append(f"    {source_modules[0]} --> {target_modules[0]}")

    lines.append("\n    %% Styling")
    lines.append("    classDef controller fill:#ff9999,stroke:#333,stroke-width:2px")
    lines.append("    classDef service fill:#99ccff,stroke:#333,stroke-width:2px")
    lines.append("    classDef repo fill:#99ff99,stroke:#333,stroke-width:2px")
    lines.append("    classDef ui fill:#ffcc99,stroke:#333,stroke-width:2px")
    lines.append("    classDef util fill:#cc99ff,stroke:#333,stroke-width:2px")
    lines.append("    classDef nav fill:#ffff99,stroke:#333,stroke-width:2px")

    style_map = {
        "Controllers": "controller",
        "Services": "service",
        "Repositories": "repo",
        "UI": "ui",
        "Utils": "util",
        "Navigators": "nav",
    }

    for category, style_class in style_map.items():
        for module_name in modules.keys():
            patterns = key_modules.get(category, [])
            if isinstance(patterns, str):
                patterns = [patterns]
            if any(pattern in module_name for pattern in patterns):
                module_id = module_name.replace(".", "_")
                lines.append(f"    class {module_id} {style_class}")

    return "\n".join(lines)


def main():
    root = Path(__file__).parent.parent
    output_dir = root / "docs" / "diagrams"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Analyzing codebase structure...")
    modules = analyze_directory(root)
    print(f"Found {len(modules)} modules")

    print("Categorizing modules...")
    categories = categorize_modules(modules)
    for category, module_list in categories.items():
        print(f"  {category}: {len(module_list)} modules")

    print("Analyzing dependencies...")
    dependencies = find_dependencies(modules)

    print("Generating Mermaid diagram...")
    mermaid = generate_mermaid(categories, dependencies, modules)

    output_file = output_dir / "architecture.mmd"
    with open(output_file, "w") as f:
        f.write(mermaid)

    print(f"✓ Architecture diagram generated: {output_file}")
    print("\nTo view: paste contents into https://mermaid.live/")


if __name__ == "__main__":
    main()
