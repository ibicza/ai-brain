"""Generate the deterministic M-34.2 development corpus (never the final corpus)."""

from __future__ import annotations

import argparse
from pathlib import Path


def _positive() -> str:
    methods = []
    patterns = (
        lambda i: f'public String p{i:03d}(int value) {{ return ""; }}',
        lambda i: (
            f"public java.util.List<String> p{i:03d}(java.util.List<String> value) {{ return value; }}"
        ),
        lambda i: (
            f"public java.util.Map.Entry<String,Integer> p{i:03d}(java.util.Map.Entry<String,Integer> value) {{ return value; }}"
        ),
        lambda i: f"public Nested p{i:03d}(Nested value) {{ return value; }}",
        lambda i: f"public String[] p{i:03d}(String... value) {{ return value; }}",
        lambda i: f"public String[] p{i:03d}(String[] value) {{ return value; }}",
        lambda i: f"public <T extends Number> T p{i:03d}(T value) {{ return value; }}",
        lambda i: (
            f"public <T extends Number> T[][] p{i:03d}(T[]... value) {{ return value; }}"
        ),
        lambda i: (
            f"public java.time.Instant p{i:03d}(java.time.Instant value) {{ return value; }}"
        ),
        lambda i: f"public boolean p{i:03d}(Object value) {{ return value != null; }}",
    )
    for index in range(299):
        methods.append("    " + patterns[index % len(patterns)](index))
    return "\n".join(
        (
            "package dev.m342.positive;",
            "public class PositiveCorpus {",
            "    public static class Nested {}",
            "    public PositiveCorpus() {}",
            *methods,
            "}",
            "",
        )
    )


def _methods(prefix: str, source_type: str, count: int) -> tuple[str, ...]:
    return tuple(
        f"    public void {prefix}{index:03d}({source_type} value) {{}}"
        for index in range(count)
    )


def _unit(package: str, name: str, imports: tuple[str, ...], methods) -> str:
    return "\n".join(
        (
            f"package {package};",
            *(f"import {value};" for value in imports),
            f"public class {name} {{",
            *methods,
            "}",
            "",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = {
        "positive/PositiveCorpus.java": _positive(),
        "negative/ForeignUnimported.java": _unit(
            "dev.m342.negative",
            "ForeignUnimported",
            (),
            _methods("foreign", "Widget", 60),
        ),
        "negative/MissingFqn.java": _unit(
            "dev.m342.negative",
            "MissingFqn",
            (),
            _methods("fqn", "missing.pkg.Type", 60),
        ),
        "negative/MissingExplicit.java": _unit(
            "dev.m342.negative",
            "MissingExplicit",
            ("missing.pkg.Imported",),
            _methods("explicit", "Imported", 60),
        ),
        "negative/MissingSimple.java": _unit(
            "dev.m342.negative",
            "MissingSimple",
            (),
            _methods("simple", "AbsentType", 60),
        ),
        "negative/WildcardAmbiguous.java": _unit(
            "dev.m342.negative",
            "WildcardAmbiguous",
            ("dev.m342.alpha.*", "dev.m342.beta.*"),
            _methods("wildcard", "Value", 60),
        ),
        "support/Widget.java": "package dev.m342.foreign;\npublic class Widget {}\n",
        "support/AlphaValue.java": "package dev.m342.alpha;\nclass Value {}\n",
        "support/BetaValue.java": "package dev.m342.beta;\nclass Value {}\n",
    }
    for relative, text in rows.items():
        path = args.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
