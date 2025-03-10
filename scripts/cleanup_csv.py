#!/usr/bin/env python3
"""
CSV Cleanup Script

This script deletes all CSV files from the current directory.
Use with caution as it permanently removes data files.
"""

import os
import glob
import argparse
from datetime import datetime

def cleanup_csv_files(backup=False, older_than=None):
    """
    Delete all CSV files from the current directory
    
    Args:
        backup: If True, create a backup directory with all CSV files
        older_than: If provided, only delete files older than this many days
    """
    # Find all CSV files in the current directory
    csv_files = glob.glob("*.csv")
    
    if not csv_files:
        print("No CSV files found.")
        return
    
    # Create backup if requested
    if backup:
        backup_dir = f"csv_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(backup_dir, exist_ok=True)
        print(f"Creating backup in {backup_dir}/")
    
    # Process each file
    deleted_count = 0
    for file in csv_files:
        # Check file age if needed
        if older_than:
            file_time = os.path.getmtime(file)
            file_age_days = (datetime.now().timestamp() - file_time) / (60 * 60 * 24)
            if file_age_days < older_than:
                print(f"Skipping {file} (not old enough)")
                continue
        
        # Backup file if requested
        if backup:
            import shutil
            shutil.copy2(file, os.path.join(backup_dir, file))
        
        # Delete the file
        os.remove(file)
        deleted_count += 1
        print(f"Deleted: {file}")
    
    print(f"\nCleanup complete. {deleted_count} CSV files deleted.")
    if backup and deleted_count > 0:
        print(f"Backup created in {backup_dir}/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete CSV files from the current directory")
    parser.add_argument("--backup", action="store_true", help="Create a backup before deleting")
    parser.add_argument("--older-than", type=int, help="Only delete files older than this many days")
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("CSV CLEANUP UTILITY")
    print("=" * 50)
    
    if not args.backup:
        confirm = input("⚠️  WARNING: This will permanently delete CSV files! Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Operation cancelled.")
            exit(0)
    
    cleanup_csv_files(backup=args.backup, older_than=args.older_than) 