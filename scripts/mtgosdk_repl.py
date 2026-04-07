"""Inspect pythonnet coreclr bootstrap state."""

from __future__ import annotations

import importlib
import time
from pathlib import Path

try:
    import pythonnet
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("pythonnet is not installed in this environment.") from exc

pythonnet.load("coreclr")

clr = importlib.import_module("clr")  # type: ignore
AppDomain = importlib.import_module("System").AppDomain  # type: ignore


def _candidate_dirs() -> list[Path]:
    dotnet_root = Path(r"C:\Program Files\dotnet")
    reference_root = Path(
        r"C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework"
    )
    dirs: list[Path] = []

    windows_desktop = dotnet_root / "shared" / "Microsoft.WindowsDesktop.App"
    for version in ("9.0.10", "9.0.2", "8.0.13", "6.0.36"):
        candidate = windows_desktop / version
        if candidate.exists():
            dirs.append(candidate)

    netcore_app = dotnet_root / "shared" / "Microsoft.NETCore.App"
    if netcore_app.exists():
        for version in ("9.0.10", "9.0.2", "8.0.13", "6.0.36"):
            candidate = netcore_app / version
            if candidate.exists():
                dirs.append(candidate)

    for version in ("v4.8.1", "v4.8", "v4.7.2", "v4.7.1", "v4.6.2", "v4.6"):
        netfx = reference_root / version
        if netfx.exists():
            dirs.append(netfx)
            facades = netfx / "Facades"
            if facades.exists():
                dirs.append(facades)

    return dirs


def _add_reference(name: str, candidate_dirs: list[Path]) -> None:
    for directory in candidate_dirs:
        dll = directory / f"{name}.dll"
        if dll.exists():
            clr.AddReference(str(dll))
            return
    clr.AddReference(name)


_shared_dirs = _candidate_dirs()
for _assembly in ("WindowsBase", "PresentationCore", "PresentationFramework", "System.Xaml"):
    _add_reference(_assembly, _shared_dirs)

_publish_dir = Path(
    r"C:\Users\Pedro\Documents\GitHub\magic_online_metagame_crawler\dotnet\MTGOBridge\bin\Release\net9.0-windows7.0\win-x64\publish"
)
for _dll in ("MTGOSDK.Win32.dll", "MTGOSDK.dll"):
    _path = _publish_dir / _dll
    if not _path.exists():
        raise SystemExit(f"Missing expected bridge assembly: {_path}")
    clr.AddReference(str(_path))

del _assembly, _dll, _path, _publish_dir, _shared_dirs

print(
    "MTGOSDK loaded; call list_mtgosdk_namespaces(), list_methods_by_type(), or generate_stubs() for inspection."
)


def explain_namespace_visibility() -> str:
    """Explain why dir(MTGOSDK) omits the 'API' module."""
    assembly = _get_mtgosdk_assembly()
    namespaces = sorted(
        {
            dtype.Namespace
            for dtype in assembly.GetTypes()
            if dtype.Namespace and dtype.Namespace.startswith("MTGOSDK.")
        }
    )
    return (
        "pythonnet surfaces .NET namespaces lazily. Attributes such as 'API' are created on-demand "
        "when you first access them (e.g., 'import MTGOSDK.API'), so they do not appear in dir(MTGOSDK) "
        "until they are accessed. "
        f"Namespaces exported by MTGOSDK: {namespaces}"
    )


def list_mtgosdk_namespaces() -> list[str]:
    """Return sorted MTGOSDK namespace names discovered from the loaded assembly."""
    assembly = _get_mtgosdk_assembly()
    namespaces = sorted(
        {
            dtype.Namespace
            for dtype in assembly.GetTypes()
            if dtype.Namespace and dtype.Namespace.startswith("MTGOSDK.")
        }
    )
    try:
        base_dir = Path(__file__).resolve().parent
    except NameError:
        base_dir = Path.cwd()
    output_path = base_dir / "mtgosdk_namespaces.txt"
    output_path.write_text("\n".join(namespaces), encoding="utf-8")
    print(f"Wrote {len(namespaces)} namespaces to {output_path}")
    return namespaces


def _get_mtgosdk_assembly():
    for assembly in AppDomain.CurrentDomain.GetAssemblies():
        if assembly.GetName().Name == "MTGOSDK":
            return assembly
    raise RuntimeError("MTGOSDK assembly is not loaded.")


def list_methods_by_type(include_inherited: bool = False) -> None:
    """Print every public method for each MTGOSDK type."""
    from System.Reflection import BindingFlags  # type: ignore

    output_lines: list[str] = []

    def _format_type(dtype) -> str:
        name = dtype.FullName or dtype.Name
        if dtype.IsGenericType:
            generic_args = ", ".join(_format_type(arg) for arg in dtype.GetGenericArguments())
            base = (
                dtype.GetGenericTypeDefinition().FullName or dtype.GetGenericTypeDefinition().Name
            )
            base = base.split("`", 1)[0]
            return f"{base}<{generic_args}>"
        return name

    def _format_parameter(param) -> str:
        prefix = []
        if param.IsOut:
            prefix.append("out")
        elif param.ParameterType.IsByRef:
            prefix.append("ref")
        if param.IsOptional:
            prefix.append("[optional]")
        type_name = _format_type(
            param.ParameterType.GetElementType()
            if param.ParameterType.IsByRef
            else param.ParameterType
        )
        prefix.append(type_name)
        prefix.append(param.Name or "_")
        return " ".join(prefix)

    flags = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public
    if not include_inherited:
        flags |= BindingFlags.DeclaredOnly

    assembly = _get_mtgosdk_assembly()
    for typ in assembly.GetTypes():
        if not typ.Namespace or not typ.Namespace.startswith("MTGOSDK."):
            continue
        methods = typ.GetMethods(flags)
        if not methods:
            continue
        header = f"{typ.FullName}:"
        print(header)
        output_lines.append(header)
        for method in methods:
            parameters = ", ".join(_format_parameter(param) for param in method.GetParameters())
            return_type = _format_type(method.ReturnType) if method.ReturnType else "void"
            line = f"  - {method.Name}({parameters}) -> {return_type}"
            print(line)
            output_lines.append(line)
    base_dir = Path.cwd()
    try:
        base_dir = Path(__file__).resolve().parent
    except NameError:
        base_dir = Path.cwd()
    output_path = base_dir / "mtgosdk_methods.txt"
    output_path.write_text("\n".join(output_lines), encoding="utf-8")
    print(f"\nWrote {len(output_lines)} lines to {output_path}")


def _current_trade():
    """Return the active TradeEscrow instance (if any)."""
    from MTGOSDK.API.Trade import TradeManager  # type: ignore

    return TradeManager.CurrentTrade


def _require_trade():
    trade = _current_trade()
    if trade is None:
        raise RuntimeError("TradeManager.CurrentTrade returned null. Start a trade first.")
    return trade


def _sum_item_quantities(collection) -> int:
    """Sum Quantity/Count attributes from a TradeEscrow collection."""
    if collection is None:
        return 0

    try:
        iterable = collection.CollectionItems
    except AttributeError:
        iterable = getattr(collection, "Items", None)

    total = 0
    if not iterable:
        return total

    for entry in iterable:
        if entry is None:
            continue
        quantity = (
            getattr(entry, "Quantity", None)
            or getattr(entry, "Count", None)
            or getattr(entry, "Amount", None)
        )
        try:
            total += int(quantity or 0)
        except (TypeError, ValueError):
            continue
    return total


def accept_trade() -> None:
    """Documented placeholder for trade acceptance (see docs/api-reference.md#trade)."""
    trade = _current_trade()
    if trade is None:
        print("No active trade; TradeManager.CurrentTrade is null.")
        return

    # The MTGOSDK trade section (docs/api-reference.md#trade) only exposes read-only escrow
    # metadata, so there is no public API surface we can call to submit acceptance.
    raise NotImplementedError(
        "Trade acceptance is not exposed by MTGOSDK; monitor docs/api-reference.md#trade for updates."
    )


def wait_for_bot_to_take_cards(
    *,
    expected_partner_cards: int | None = None,
    timeout: float = 180.0,
    poll_interval: float = 1.5,
) -> dict[str, float | int | str | None]:
    """Poll TradeEscrow.TradedItems until the local stack is empty."""

    start = time.monotonic()
    deadline = start + timeout

    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(
                "Timed out waiting for the bot to remove cards from the trade window."
            )

        trade = _current_trade()
        if trade is None:
            raise RuntimeError("Trade closed while waiting for the bot to take cards.")

        local_total = _sum_item_quantities(getattr(trade, "TradedItems", None))
        partner_total = _sum_item_quantities(getattr(trade, "PartnerTradedItems", None))

        if local_total == 0 and (
            expected_partner_cards is None or partner_total >= expected_partner_cards
        ):
            elapsed = time.monotonic() - start
            state = getattr(trade, "State", None)
            print(
                f"Bot removed all cards after {elapsed:.1f}s "
                f"(state={state}, partner_cards={partner_total})."
            )
            return {
                "elapsed_seconds": round(elapsed, 2),
                "partner_cards": partner_total,
                "state": str(state),
            }

        time.sleep(poll_interval)


def generate_stubs(
    output_dir: Path | str | None = None, sample_namespace: str | None = None
) -> None:
    """Generate .pyi stub files for MTGOSDK namespaces."""
    if output_dir is None:
        try:
            base_dir = Path(__file__).resolve().parent.parent
        except NameError:
            base_dir = Path.cwd()
        output_dir = base_dir / "stubs" / "MTGOSDK"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    assembly = _get_mtgosdk_assembly()

    # Group types by namespace
    namespaces: dict[str, list] = {}
    for typ in assembly.GetTypes():
        if not typ.Namespace or not typ.Namespace.startswith("MTGOSDK."):
            continue
        # Skip compiler-generated and nested types for simplicity
        if "+" in typ.FullName or "<" in typ.FullName:
            continue
        if sample_namespace and typ.Namespace != sample_namespace:
            continue

        if typ.Namespace not in namespaces:
            namespaces[typ.Namespace] = []
        namespaces[typ.Namespace].append(typ)

    if not namespaces:
        print(f"No namespaces found{f' matching {sample_namespace}' if sample_namespace else ''}")
        return

    # Generate __init__.pyi for root
    root_init = output_dir / "__init__.pyi"
    root_init.write_text("# MTGOSDK stub root\n", encoding="utf-8")
    print(f"Generated {root_init}")

    # Generate stub for each namespace
    for namespace, types in namespaces.items():
        stub_content = _generate_namespace_stub(namespace, types)

        # Convert MTGOSDK.API.Collection to API/Collection/__init__.pyi
        parts = namespace.split(".")
        namespace_parts = parts[1:]  # Skip 'MTGOSDK'

        if namespace_parts:
            file_path = output_dir / Path(*namespace_parts) / "__init__.pyi"
        else:
            file_path = output_dir / "__init__.pyi"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(stub_content, encoding="utf-8")
        print(f"Generated {file_path} ({len(types)} types)")

    print(f"\nStub generation complete! Generated stubs in {output_dir}")
    print(f"Total namespaces: {len(namespaces)}")


def _generate_namespace_stub(namespace: str, types: list) -> str:
    """Generate stub content for a single namespace."""
    lines = [
        f'"""Auto-generated stub for {namespace}"""',
        "from __future__ import annotations",
        "",
        "from typing import Any, Iterable, Optional",
        "from datetime import datetime",
        "",
    ]

    # Sort types: enums first, then classes, then interfaces
    sorted_types = sorted(
        types, key=lambda t: (0 if t.IsEnum else 1 if not t.IsInterface else 2, t.Name)
    )

    for typ in sorted_types:
        try:
            lines.append(_generate_class_stub(typ))
            lines.append("")
        except Exception as e:
            lines.append(f"# ERROR generating stub for {typ.Name}: {e}")
            lines.append("")

    return "\n".join(lines)


def _generate_class_stub(typ) -> str:
    """Generate stub for a single class/enum/interface."""
    from System.Reflection import BindingFlags  # type: ignore

    lines = []

    # Handle enums
    if typ.IsEnum:
        lines.append(f"class {typ.Name}:")
        lines.append('    """' + (typ.FullName or typ.Name) + '"""')
        for field in typ.GetFields(BindingFlags.Public | BindingFlags.Static):
            if field.IsLiteral:  # Enum values
                lines.append(f"    {field.Name}: {typ.Name}")
        if len(lines) == 2:  # Only header and docstring
            lines.append("    pass")
        return "\n".join(lines)

    # Class/Interface definition
    base_classes = []
    if typ.BaseType and typ.BaseType.FullName not in ("System.Object", "System.ValueType"):
        base_name = _simplify_type_name(typ.BaseType)
        if base_name != "object":
            base_classes.append(base_name)

    # Add interfaces
    for interface in typ.GetInterfaces():
        interface_name = _simplify_type_name(interface)
        if interface_name not in base_classes and not interface_name.startswith("System."):
            base_classes.append(interface_name)

    if base_classes:
        lines.append(f"class {typ.Name}({', '.join(base_classes)}):")
    else:
        lines.append(f"class {typ.Name}:")

    lines.append('    """' + (typ.FullName or typ.Name) + '"""')

    flags = (
        BindingFlags.Instance
        | BindingFlags.Static
        | BindingFlags.Public
        | BindingFlags.DeclaredOnly
    )

    # Fields (public constants)
    fields = typ.GetFields(flags)
    for field in fields:
        if field.IsLiteral or (field.IsStatic and field.IsInitOnly):  # Constants
            field_type = _map_dotnet_type_to_python(field.FieldType)
            lines.append(f"    {field.Name}: {field_type}")

    # Properties
    props = typ.GetProperties(flags)
    for prop in props:
        if prop.GetIndexParameters().Length > 0:  # Indexer property
            continue
        prop_type = _map_dotnet_type_to_python(prop.PropertyType)

        # Static property
        if (prop.GetMethod and prop.GetMethod.IsStatic) or (
            prop.SetMethod and prop.SetMethod.IsStatic
        ):
            lines.append("    @staticmethod")
            lines.append(f"    def {prop.Name}() -> {prop_type}: ...")
        else:
            lines.append("    @property")
            lines.append(f"    def {prop.Name}(self) -> {prop_type}: ...")
            if prop.CanWrite:
                lines.append(f"    @{prop.Name}.setter")
                lines.append(f"    def {prop.Name}(self, value: {prop_type}) -> None: ...")

    # Constructor
    constructors = typ.GetConstructors(BindingFlags.Public | BindingFlags.Instance)
    for ctor in constructors:
        params = []
        for param in ctor.GetParameters():
            param_type = _map_dotnet_type_to_python(param.ParameterType)
            param_name = param.Name or f"arg{len(params)}"
            default = ""
            if param.IsOptional:
                default = " = ..."
            params.append(f"{param_name}: {param_type}{default}")

        params_str = ", ".join(params)
        if params_str:
            params_str = ", " + params_str
        lines.append(f"    def __init__(self{params_str}) -> None: ...")

    # Methods
    methods = typ.GetMethods(flags)
    seen_methods = set()
    for method in methods:
        if method.IsSpecialName:  # Skip property getters/setters, operators
            continue

        # Create method signature for deduplication
        method_sig = f"{method.Name}_{method.GetParameters().Length}"
        if method_sig in seen_methods:
            continue
        seen_methods.add(method_sig)

        try:
            method_stub = _generate_method_stub(method)
        except Exception as exc:
            print(f"Skipping method stub for {method.Name}: {exc}")
        else:
            lines.append(f"    {method_stub}")

    if len(lines) == 2:  # Only class definition and docstring
        lines.append("    pass")

    return "\n".join(lines)


def _generate_method_stub(method) -> str:
    """Generate stub for a method."""
    params = []
    for param in method.GetParameters():
        param_type = _map_dotnet_type_to_python(param.ParameterType)
        param_name = param.Name or f"arg{len(params)}"
        default = ""
        if param.IsOptional:
            default = " = ..."
        params.append(f"{param_name}: {param_type}{default}")

    params_str = ", ".join(params)

    # Static method
    decorator = ""
    if method.IsStatic:
        decorator = "@staticmethod\n    "
        if params_str:
            params_str = params_str
        signature = f"def {method.Name}({params_str})"
    else:
        if params_str:
            params_str = ", " + params_str
        signature = f"def {method.Name}(self{params_str})"

    return_type = _map_dotnet_type_to_python(method.ReturnType)
    return f"{decorator}{signature} -> {return_type}: ..."


def _simplify_type_name(dotnet_type) -> str:
    """Get simplified type name for inheritance."""
    if dotnet_type.IsGenericType:
        base_name = dotnet_type.Name.split("`")[0]
        return base_name
    return dotnet_type.Name


def _map_dotnet_type_to_python(dotnet_type) -> str:
    """Map .NET types to Python type hints."""
    if dotnet_type is None:
        return "None"

    name = dotnet_type.Name
    full_name = dotnet_type.FullName or name

    # Handle common .NET types
    type_map = {
        "String": "str",
        "Int32": "int",
        "Int64": "int",
        "UInt32": "int",
        "UInt64": "int",
        "Int16": "int",
        "UInt16": "int",
        "Byte": "int",
        "SByte": "int",
        "Boolean": "bool",
        "Double": "float",
        "Single": "float",
        "Decimal": "float",
        "DateTime": "datetime",
        "Void": "None",
        "Object": "Any",
        "Char": "str",
        "Guid": "str",
        "TimeSpan": "float",
    }

    if name in type_map:
        return type_map[name]

    # Handle arrays
    if dotnet_type.IsArray:
        element_type = _map_dotnet_type_to_python(dotnet_type.GetElementType())
        return f"list[{element_type}]"

    # Handle generics
    if dotnet_type.IsGenericType:
        generic_def = dotnet_type.GetGenericTypeDefinition().Name.split("`")[0]
        generic_args = [
            _map_dotnet_type_to_python(arg) for arg in dotnet_type.GetGenericArguments()
        ]

        generic_map = {
            "List": f"list[{generic_args[0]}]" if generic_args else "list[Any]",
            "IEnumerable": f"Iterable[{generic_args[0]}]" if generic_args else "Iterable[Any]",
            "ICollection": f"Iterable[{generic_args[0]}]" if generic_args else "Iterable[Any]",
            "IList": f"list[{generic_args[0]}]" if generic_args else "list[Any]",
            "Dictionary": (
                f"dict[{generic_args[0]}, {generic_args[1]}]"
                if len(generic_args) >= 2
                else "dict[Any, Any]"
            ),
            "IDictionary": (
                f"dict[{generic_args[0]}, {generic_args[1]}]"
                if len(generic_args) >= 2
                else "dict[Any, Any]"
            ),
            "Nullable": f"Optional[{generic_args[0]}]" if generic_args else "Optional[Any]",
        }

        if generic_def in generic_map:
            return generic_map[generic_def]

        # Generic type we don't recognize - use the base name
        return generic_def

    # By-ref parameters
    if dotnet_type.IsByRef:
        element_type = _map_dotnet_type_to_python(dotnet_type.GetElementType())
        return element_type

    # Pointer types
    if dotnet_type.IsPointer:
        return "Any"

    # For MTGOSDK types, use the simple name
    if full_name and full_name.startswith("MTGOSDK."):
        return name

    # System types - use simple name
    if full_name and full_name.startswith("System."):
        return "Any"

    return name
