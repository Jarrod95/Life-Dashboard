"""Local finance import CLI; never writes to the source workbook."""
import argparse
import json
import os
from app import create_app
from app.importer import import_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=os.getenv("LIFE_FINANCE_XLSX_PATH"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if not args.file:
        parser.error("--file or LIFE_FINANCE_XLSX_PATH is required")
    with create_app().app_context():
        result = import_path(args.file, dry_run=args.dry_run, force=args.force)
        print(json.dumps(result, indent=2, default=str))
        if args.verbose:
            print("Source workbook was not modified.")

if __name__ == "__main__":
    main()
