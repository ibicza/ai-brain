"""Generate the deterministic mixed M-34.3 development corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

OPENJDK_SOURCE_ARCHIVE_SHA256 = (
    "658d6fe751ad9fc23d40a129654e2b26931209babf5ff7802273f3c468674e52"
)
OPENJDK_SOURCE_SELECTION = (
    ("java.base/", 25),
    ("java.compiler/", 6),
    ("java.desktop/", 19),
)


def _write(path: Path, text: str, newline: str = "\n", final_newline: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    value = text.rstrip("\r\n") + ("\n" if final_newline else "")
    if newline != "\n":
        value = value.replace("\n", newline)
    path.write_bytes(value.encode("utf-8"))


def _write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _install_openjdk_sources(output: Path, source_archive: Path) -> None:
    archive_bytes = source_archive.read_bytes()
    archive_hash = hashlib.sha256(archive_bytes).hexdigest()
    if archive_hash != OPENJDK_SOURCE_ARCHIVE_SHA256:
        raise ValueError(
            "OpenJDK source archive hash mismatch: "
            f"expected {OPENJDK_SOURCE_ARCHIVE_SHA256}, got {archive_hash}"
        )
    selected: list[dict[str, str]] = []
    with zipfile.ZipFile(source_archive) as archive:
        names = sorted(
            name for name in archive.namelist() if name.endswith("/package-info.java")
        )
        for module_prefix, required_count in OPENJDK_SOURCE_SELECTION:
            candidates = [name for name in names if name.startswith(module_prefix)]
            if len(candidates) < required_count:
                raise ValueError(
                    f"not enough package-info sources for {module_prefix}: "
                    f"{len(candidates)} < {required_count}"
                )
            for name in candidates[:required_count]:
                value = archive.read(name)
                _write_bytes(output / "real" / "openjdk-25" / name, value)
                selected.append(
                    {
                        "archive_path": name,
                        "bytes_hash": hashlib.sha256(value).hexdigest(),
                    }
                )
    provenance = {
        "archive_sha256": archive_hash,
        "distribution": "OpenJDK 25.0.2 source archive",
        "license": "GPL-2.0-only WITH Classpath-exception-2.0",
        "real_source_count": len(selected),
        "schema_version": 1,
        "selected_sources": selected,
        "selection": [list(item) for item in OPENJDK_SOURCE_SELECTION],
    }
    _write(
        output / "OPENJDK_PROVENANCE.json",
        json.dumps(provenance, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )
    _write(
        output / "NOTICE.md",
        """# M-34.3 development corpus provenance

The files below `real/openjdk-25/` are unmodified source units selected from
the OpenJDK 25.0.2 `src.zip` archive pinned in `OPENJDK_PROVENANCE.json`.
Their upstream file headers carry the GPLv2 plus Classpath Exception notice.
All `synthetic/` and `support/` sources are deterministic M-34.3 fixtures.
""",
    )


def _positive(index: int) -> str:
    package = f"dev.m343.liba.p{index % 5}" if index < 13 else f"dev.m343.libb.p{index % 5}"
    name = f"RealCatalog{index:02d}"
    methods = []
    for group in range(4):
        method = f"overload{group}"
        methods.extend(
            (
                f"    public int {method}(int value) {{ return value; }}",
                f"    public long {method}(long value) {{ return value; }}",
                f"    public String {method}(String value) {{ return value; }}",
                f"    public Object {method}(Object value) {{ return value; }}",
            )
        )
    methods.extend(
        (
            "    public <T extends Number> T genericNumber(T value) { return value; }",
            "    public <T> T genericIdentity(T value) { return value; }",
            "    public <T extends Number & Comparable<T>> T intersection(T value) { return value; }",
            "    public String risky(String value) throws IOException { return value; }",
            "    public void close(int value) throws IllegalStateException {}",
            "    public boolean booleanValue(boolean value) { return value; }",
            "    public int integerValue(char value) { return value; }",
            "    public double decimalValue(float value) { return value; }",
            "    public String stringValue(CharSequence value) { return value.toString(); }",
            "    public Object entityValue(Object value) { return value; }",
            "    public String[][] arrayValue(String[]... value) { return value; }",
            "    public void voidValue() {}",
            "    public Nested nestedValue(Nested value) { return value; }",
            "    public String varargs(String... values) { return values.length == 0 ? \"\" : values[0]; }",
            "    public java.util.List<String> listValue(java.util.List<String> value) { return value; }",
            "    public java.util.Map<String,Integer> mapValue(java.util.Map<String,Integer> value) { return value; }",
            "    public java.util.Map.Entry<String,Integer> entryValue(java.util.Map.Entry<String,Integer> value) { return value; }",
            "    public String μέτρο(String τιμή) { return τιμή; }",
        )
    )
    for value in range(12):
        methods.append(
            f"    public int operation{value:02d}(int left, int right) {{ return left + right + {value}; }}"
        )
    if index == 0:
        methods.append(
            '    @Deprecated(since = "21", forRemoval = false)\n'
            "    public String legacyValue(String value) { return value; }"
        )
        methods.append(
            "    public int bodyOnlyError() { return missingBodySymbol; }"
        )
        methods.append(
            '    public String textBlock() { return """\n        { // text, not comment /* */ }\n        """; }'
        )
    return "\n".join(
        (
            f"package {package};",
            "import java.io.IOException;",
            "import java.util.*;",
            "import java.util.Map.Entry;",
            "import static java.util.Collections.emptyList;",
            f"public class {name} {{",
            "    public static class Nested {",
            "        public Nested self(Nested value) { return value; }",
            "    }",
            f"    public {name}() {{}}",
            f"    public {name}(int seed) {{}}",
            *methods,
            "}",
        )
    )


def _negative(index: int) -> str:
    package = f"dev.m343.mutations.p{index % 5}"
    name = f"NegativeCatalog{index:02d}"
    imports = []
    if 10 <= index < 15:
        imports.append("import dev.m343.hidden.HiddenType;")
        source_type = "HiddenType"
        prefix = "inaccessible"
    elif 15 <= index < 20:
        imports.append("import dev.m343.hidden.HiddenSupport.PrivateNested;")
        source_type = "PrivateNested"
        prefix = "privateNested"
    elif 20 <= index < 23:
        imports.append("import sun.nio.ch.DirectBuffer;")
        source_type = "DirectBuffer"
        prefix = "nonExported"
    elif index == 23:
        source_type = "dev.m343.hidden.LocalOwner.LocalThing"
        prefix = "localFqn"
    elif index == 24:
        imports.append("import static java.util.Collections.emptyList;")
        source_type = "emptyList"
        prefix = "staticImport"
    elif index < 5:
        source_type = f"T{index}"
        prefix = "invalidBound"
    elif index < 10:
        source_type = f"MissingException{index}"
        prefix = "invalidThrows"
    else:
        source_type = "MissingType"
        prefix = "missing"
    methods = []
    for value in range(20):
        if index < 5:
            methods.append(
                f"    public <T{index} extends MissingBound{index}> T{index} {prefix}{value:02d}(T{index} value) {{ return value; }}"
            )
        elif 5 <= index < 10:
            methods.append(
                f"    public void {prefix}{value:02d}() throws {source_type} {{}}"
            )
        else:
            methods.append(f"    public void {prefix}{value:02d}({source_type} value) {{}}")
    return "\n".join(
        (
            f"package {package};",
            *imports,
            f"public class {name} {{",
            *methods,
            "}",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jdk-source-archive", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        shutil.rmtree(args.output)
    _install_openjdk_sources(args.output, args.jdk_source_archive)
    for index in range(25):
        newline = "\r\n" if index == 1 else "\n"
        _write(
            args.output
            / f"synthetic/library-{index // 13 + 1}/p{index % 5}/RealCatalog{index:02d}.java",
            _positive(index),
            newline=newline,
            final_newline=index != 2,
        )
        _write(
            args.output / f"synthetic/mutations/p{index % 5}/NegativeCatalog{index:02d}.java",
            _negative(index),
            newline="\r" if index == 24 else "\n",
        )
    _write(
        args.output / "support/hidden/HiddenSupport.java",
        """package dev.m343.hidden;
public class HiddenSupport { private static class PrivateNested {} }
class HiddenType {}
""",
    )
    _write(
        args.output / "support/hidden/LocalOwner.java",
        """package dev.m343.hidden;
public class LocalOwner {
    public void host() { class LocalThing {} }
}
""",
    )
    _write(
        args.output / "support/annotations/Mark.java",
        """package dev.m343.support;
import java.lang.annotation.*;
@Target({ElementType.TYPE_USE, ElementType.METHOD})
public @interface Mark {}
""",
    )
    _write(
        args.output / "synthetic/library-1/shared/Service.java",
        """package dev.m343.liba.shared;
public interface Service {
    default boolean ready() { return true; }
    static int version() { return 1; }
}
""",
    )
    _write(
        args.output / "synthetic/library-2/shared/Service.java",
        """package dev.m343.libb.shared;
public record Service(String name, int version) {
    public Service { if (name == null) throw new IllegalArgumentException(); }
    public String label() { return name + version; }
}
""",
    )


if __name__ == "__main__":
    main()
