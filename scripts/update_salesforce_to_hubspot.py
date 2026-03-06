#!/usr/bin/env python3
"""
Script to replace all Salesforce references with HubSpot across documentation files.

Replacements:
- "Salesforce" → "HubSpot"
- "sf_" → "hs_"
- "JWT Bearer Flow" → "Private App token"
- "Connected App" → "Private App"
- "Case" → "Deal" (when referring to CRM objects)
- "Account" → "Company" (when referring to CRM objects)
- "SF_" → "HS_" (in env var names)
"""

import re
from pathlib import Path

# Define the root directory
ROOT_DIR = Path("/home/aparna/Desktop/invoicify")

# Files to update (only root .md files)
FILES_TO_UPDATE = [
    "README.md",
    "DEPLOY.md",
    "DEPLOYMENT_GUIDE.md",
    "IMPLEMENTATION_SUMMARY.md",
    "prd.md",
    "ARCHITECTURE.md",
    "CONTRACT_VERIFICATION.md",
]

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
    
    # Environment variables
    (r"SF_", "HS_"),
    (r"sf_", "hs_"),
    
    # CRM object references (case-sensitive, word boundaries)
    # Only replace when it's clearly referring to CRM objects
    (r"\bCase\b", "Deal"),
    (r"\bAccount\b", "Company"),
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
            for match in matches:
                changes_made.append(f"  '{match}' → '{replacement}'")
    
    if content != original_content:
        file_path.write_text(content)
        return len(changes_made), changes_made
    
    return 0, []

def main():
    """Main function to update all files."""
    print("=" * 80)
    print("SALESFORCE → HUBSPOT DOCUMENTATION UPDATE")
    print("=" * 80)
    print()
    
    total_files_updated = 0
    total_replacements = 0
    failed_files = []
    
    for filename in FILES_TO_UPDATE:
        file_path = ROOT_DIR / filename
        print(f"Processing: {filename}")
        
        count, changes = update_file(file_path)
        
        if count > 0:
            total_files_updated += 1
            total_replacements += count
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
    print(f"Files updated: {total_files_updated}")
    print(f"Total replacements: {total_replacements}")
    
    if failed_files:
        print(f"\nFiles that couldn't be updated:")
        for file in failed_files:
            print(f"  - {file}")
    else:
        print("\nAll files processed successfully!")
    
    print()
    return total_files_updated, failed_files

if __name__ == "__main__":
    main()
