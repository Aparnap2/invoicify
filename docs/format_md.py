#!/usr/bin/env python3
"""
Markdown formatter for documentation files.
Ensures consistent formatting across all docs.
"""

import re
import sys
from pathlib import Path


def format_markdown(content: str) -> str:
    """Format markdown content with consistent style."""

    # Ensure headers have proper spacing
    content = re.sub(r"^(#{1,6})([^\s])", r"\1 \2", content, flags=re.MULTILINE)

    # Ensure code blocks have language specification
    content = re.sub(r"^```\s*$", "```text", content, flags=re.MULTILINE)

    # Remove trailing whitespace
    content = re.sub(r"[ \t]+$", "", content, flags=re.MULTILINE)

    # Ensure single blank line before headers
    content = re.sub(r"\n{3,}(#{1,6})", r"\n\n\1", content)

    # Ensure single blank line after headers
    content = re.sub(r"(#{1,6}.*)\n{3,}", r"\1\n\n", content)

    # Format tables - ensure proper spacing
    lines = content.split("\n")
    formatted_lines = []
    in_table = False

    for line in lines:
        # Table row detection
        if "|" in line and not line.startswith("```"):
            if not in_table:
                # Add blank line before table
                if formatted_lines and formatted_lines[-1] != "":
                    formatted_lines.append("")
                in_table = True
            # Clean up table row spacing
            line = (
                "| " + " | ".join(cell.strip() for cell in line.split("|")[1:-1]) + " |"
            )
        else:
            if in_table and line.strip() and not line.startswith("|"):
                # Add blank line after table
                formatted_lines.append("")
                in_table = False

        formatted_lines.append(line)

    content = "\n".join(formatted_lines)

    # Ensure file ends with single newline
    content = content.rstrip() + "\n"

    return content


def process_file(filepath: Path) -> bool:
    """Process a single markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            original = f.read()

        formatted = format_markdown(original)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(formatted)

        return True
    except Exception as e:
        print(f"❌ Error processing {filepath}: {e}")
        return False


def main():
    """Format all markdown files in docs folder."""
    docs_dir = Path("/home/aparna/Desktop/invoicify/docs")

    if not docs_dir.exists():
        print(f"❌ Directory not found: {docs_dir}")
        sys.exit(1)

    md_files = list(docs_dir.glob("*.md"))

    if not md_files:
        print("❌ No markdown files found")
        sys.exit(1)

    print(f"📁 Formatting {len(md_files)} markdown files...")
    print()

    success = 0
    failed = 0

    for md_file in sorted(md_files):
        if md_file.name == "README.md":
            continue

        print(f"  📝 {md_file.name}", end=" ")

        if process_file(md_file):
            print("✅")
            success += 1
        else:
            print("❌")
            failed += 1

    print()
    print(f"✅ Successfully formatted: {success}")
    if failed:
        print(f"❌ Failed: {failed}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
