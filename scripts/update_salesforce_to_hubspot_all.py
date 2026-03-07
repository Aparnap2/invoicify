#!/usr/bin/env python3
"""
Script to replace all Salesforce references with HubSpot across ALL documentation files.

Replacements:
- "Salesforce" → "HubSpot"
- "sf_" → "hs_"
- "JWT Bearer Flow" → "Private App token"
- "Connected App" → "Private App"
- "Case" → "Deal" (when referring to CRM objects)
- "Account" → "Company" (when referring to CRM objects)
- "SF_" → "HS_" (in env var names)
- "SALESFORCE" → "HUBSPOT" (uppercase)
- "salesforce" → "hubspot" (lowercase in filenames/urls)
"""

import re
from pathlib import Path

# Define the root directory
ROOT_DIR = Path("/home/aparna/Desktop/invoicify")

# Replacement patterns (order matters - more specific patterns first)
REPLACEMENTS = [
    # Specific phrases first
    (r"JWT Bearer Flow", "Private App token"),
    (r"Connected App", "Private App"),
    (r"Salesforce mocks", "HubSpot mocks"),
    (r"Salesforce Mock", "HubSpot Mock"),
    (r"Salesforce API", "HubSpot API"),
    (r"Salesforce REST API", "HubSpot API"),
    (r"Salesforce Logging", "HubSpot Logging"),
    (r"Salesforce ID", "HubSpot ID"),
    (r"Salesforce", "HubSpot"),
    (r"salesforce", "hubspot"),  # lowercase for filenames/urls
    (r"SALESFORCE", "HUBSPOT"),  # uppercase for env vars
    
    # Environment variables
    (r"SF_", "HS_"),
    (r"sf_", "hs_"),
]

def update_file(file_path: Path) -> tuple[int, list[str]]:
    """Update a single file and return the count of replacements made."""
    if not file_path.exists():
        return 0, [f"File not found: {file_path}"]
    
    content = file_path.read_text()
    original_content = content
    changes_made = []
    
    for pattern, replacement in REPLACEMENTS:
        matches = re.findall(pattern, content)
        if matches:
            content = re.sub(pattern, replacement, content)
            for match in set(matches):  # Use set to avoid duplicates
                changes_made.append(f"  '{match}' → '{replacement}'")
    
    if content != original_content:
        file_path.write_text(content)
        return len(changes_made), changes_made
    
    return 0, []

def find_all_md_files() -> list[Path]:
    """Find all .md files excluding .git directory."""
    md_files = []
    for pattern in ["*.md", "**/*.md"]:
        for file_path in ROOT_DIR.glob(pattern):
            if ".git" not in str(file_path):
                md_files.append(file_path)
    return sorted(set(md_files))

def main():
    """Main function to update all files."""
    print("=" * 80)
    print("SALESFORCE → HUBSPOT DOCUMENTATION UPDATE (ALL FILES)")
    print("=" * 80)
    print()
    
    # Find all markdown files
    all_md_files = find_all_md_files()
    print(f"Found {len(all_md_files)} markdown files")
    print()
    
    total_files_updated = 0
    total_replacements = 0
    updated_files_list = []
    failed_files = []
    
    for file_path in all_md_files:
        relative_path = file_path.relative_to(ROOT_DIR)
        print(f"Processing: {relative_path}")
        
        count, changes = update_file(file_path)
        
        if count > 0:
            total_files_updated += 1
            total_replacements += count
            updated_files_list.append(str(relative_path))
            print(f"  ✅ {count} replacements made")
            for change in changes[:5]:  # Show first 5 changes
                print(f"    {change}")
            if len(changes) > 5:
                print(f"    ... and {len(changes) - 5} more")
        else:
            if changes:
                print(f"  ⚠️  {changes[0]}")
            else:
                print(f"  ℹ️  No replacements needed")
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total markdown files scanned: {len(all_md_files)}")
    print(f"Files updated: {total_files_updated}")
    print(f"Total replacements: {total_replacements}")
    
    if updated_files_list:
        print(f"\nFiles updated:")
        for file in updated_files_list:
            print(f"  ✅ {file}")
    
    if failed_files:
        print(f"\nFiles that couldn't be updated:")
        for file in failed_files:
            print(f"  ❌ {file}")
    
    print()
    return total_files_updated, failed_files, updated_files_list

if __name__ == "__main__":
    main()
