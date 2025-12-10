#!/usr/bin/env python3
"""
Google Drive Connection Test Script

Tests Google Drive API authentication and connection for the CRO Analyzer.

Usage:
    python3 scripts/test_google_drive.py --mode [quick|full]
    python3 scripts/test_google_drive.py --mode full --folder-id YOUR_FOLDER_ID
    python3 scripts/test_google_drive.py --service-account

    quick: Basic authentication and connection test (< 5 seconds)
    full: Complete test including folder operations (10-15 seconds)
"""

import sys
import os
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path to import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))


class GoogleDriveConnectionTest:
    """Tests Google Drive API authentication and connection."""

    def __init__(self, verbose: bool = True, use_service_account: bool = False):
        self.verbose = verbose
        self.use_service_account = use_service_account
        self.results: Dict[str, bool] = {}
        self.errors: List[str] = []

    def log(self, message: str, level: str = "INFO"):
        """Print log message if verbose mode is enabled."""
        if self.verbose:
            prefix = {
                "INFO": "ℹ️ ",
                "SUCCESS": "✅",
                "ERROR": "❌",
                "WARNING": "⚠️ ",
                "TEST": "🧪"
            }.get(level, "")
            print(f"{prefix} {message}")

    def test_credentials_exist(self) -> bool:
        """Test that Google Drive credentials file exists."""
        self.log("Testing credentials file existence...", "TEST")

        try:
            from dotenv import load_dotenv
            load_dotenv()

            credentials_path = os.getenv('GOOGLE_CREDENTIALS_PATH', './service_account/')

            # Check if path exists
            if not os.path.exists(credentials_path):
                self.errors.append(f"Credentials path does not exist: {credentials_path}")
                self.log(f"Credentials path does not exist: {credentials_path}", "ERROR")
                return False

            # If it's a directory, look for service account JSON
            if os.path.isdir(credentials_path):
                json_files = list(Path(credentials_path).glob("*.json"))
                if not json_files:
                    self.errors.append(f"No JSON files found in credentials directory: {credentials_path}")
                    self.log(f"No JSON files found in credentials directory: {credentials_path}", "ERROR")
                    return False

                credentials_path = str(json_files[0])
                self.log(f"Found credentials file: {credentials_path}", "SUCCESS")
            else:
                self.log(f"Credentials file exists: {credentials_path}", "SUCCESS")

            # Verify it's a valid JSON file
            import json
            try:
                with open(credentials_path, 'r') as f:
                    creds_data = json.load(f)

                # Check for service account fields
                if self.use_service_account:
                    required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
                    missing_fields = [field for field in required_fields if field not in creds_data]

                    if missing_fields:
                        self.errors.append(f"Service account credentials missing fields: {missing_fields}")
                        self.log(f"Service account credentials missing fields: {missing_fields}", "ERROR")
                        return False

                    self.log(f"Service account credentials valid for: {creds_data.get('client_email')}", "SUCCESS")
                else:
                    self.log("OAuth2 credentials file is valid JSON", "SUCCESS")

                return True

            except json.JSONDecodeError as e:
                self.errors.append(f"Credentials file is not valid JSON: {str(e)}")
                self.log(f"Credentials file is not valid JSON: {str(e)}", "ERROR")
                return False

        except ImportError as e:
            self.errors.append(f"Required module import failed: {str(e)}")
            self.log(f"Required module import failed: {str(e)}", "ERROR")
            return False
        except Exception as e:
            self.errors.append(f"Credentials check failed: {str(e)}")
            self.log(f"Credentials check failed: {str(e)}", "ERROR")
            return False

    def test_authentication(self) -> bool:
        """Test Google Drive API authentication."""
        self.log("Testing Google Drive authentication...", "TEST")

        try:
            from utils.google_drive_client import GoogleDriveClient

            # Initialize client
            client = GoogleDriveClient(use_service_account=self.use_service_account)

            # Check if service was initialized
            if client.service is None:
                self.errors.append("Google Drive service not initialized")
                self.log("Google Drive service not initialized", "ERROR")
                return False

            auth_method = "Service Account" if self.use_service_account else "OAuth2"
            self.log(f"Successfully authenticated with Google Drive API using {auth_method}", "SUCCESS")
            return True

        except ImportError as e:
            self.errors.append(f"Google Drive client import failed: {str(e)}")
            self.log(f"Google Drive client import failed: {str(e)}", "ERROR")
            return False
        except Exception as e:
            self.errors.append(f"Authentication failed: {str(e)}")
            self.log(f"Authentication failed: {str(e)}", "ERROR")
            return False

    def test_api_connection(self) -> bool:
        """Test basic Google Drive API connection with a simple query."""
        self.log("Testing Google Drive API connection...", "TEST")

        try:
            from utils.google_drive_client import GoogleDriveClient

            client = GoogleDriveClient(use_service_account=self.use_service_account)

            # Try to query user's Drive (will list files in root, limited to 1 result)
            try:
                results = client.service.files().list(
                    pageSize=1,
                    fields="nextPageToken, files(id, name, mimeType)"
                ).execute()

                self.log("Successfully connected to Google Drive API", "SUCCESS")

                files = results.get('files', [])
                if files:
                    self.log(f"API test query returned {len(files)} file(s)", "INFO")
                else:
                    self.log("API test query returned no files (Drive may be empty or access restricted)", "WARNING")

                return True

            except Exception as api_error:
                self.errors.append(f"API query failed: {str(api_error)}")
                self.log(f"API query failed: {str(api_error)}", "ERROR")
                return False

        except Exception as e:
            self.errors.append(f"API connection test failed: {str(e)}")
            self.log(f"API connection test failed: {str(e)}", "ERROR")
            return False

    def test_folder_listing(self, folder_id: Optional[str] = None) -> bool:
        """Test listing files in a specific folder."""
        if not folder_id:
            self.log("Skipping folder listing test (no folder ID provided)", "WARNING")
            return True

        self.log(f"Testing folder listing for folder ID: {folder_id}...", "TEST")

        try:
            from utils.google_drive_client import GoogleDriveClient

            client = GoogleDriveClient(use_service_account=self.use_service_account)

            # List files in folder
            files = client.list_files_in_folder(folder_id)

            if files:
                self.log(f"Successfully listed {len(files)} files in folder", "SUCCESS")

                if self.verbose:
                    self.log(f"Sample files (showing up to 3):", "INFO")
                    for file_info in files[:3]:
                        self.log(f"  - {file_info['name']} ({file_info.get('mimeType', 'unknown type')})", "INFO")

                return True
            else:
                self.log("Folder is empty or not accessible", "WARNING")
                return True  # Not a failure, just empty

        except Exception as e:
            self.errors.append(f"Folder listing test failed: {str(e)}")
            self.log(f"Folder listing test failed: {str(e)}", "ERROR")
            return False

    def test_download_capability(self, folder_id: Optional[str] = None) -> bool:
        """Test download capability (dry run - doesn't actually download)."""
        if not folder_id:
            self.log("Skipping download test (no folder ID provided)", "WARNING")
            return True

        self.log("Testing download capability (dry run)...", "TEST")

        try:
            from utils.google_drive_client import GoogleDriveClient

            client = GoogleDriveClient(use_service_account=self.use_service_account)

            # List files in folder
            files = client.list_files_in_folder(folder_id)

            if not files:
                self.log("No files to test download with", "WARNING")
                return True

            # Check if client has download methods
            if not hasattr(client, 'download_file'):
                self.errors.append("GoogleDriveClient missing download_file method")
                self.log("GoogleDriveClient missing download_file method", "ERROR")
                return False

            if not hasattr(client, 'download_google_doc_as_docx'):
                self.errors.append("GoogleDriveClient missing download_google_doc_as_docx method")
                self.log("GoogleDriveClient missing download_google_doc_as_docx method", "ERROR")
                return False

            self.log("Download methods are available on client", "SUCCESS")
            self.log(f"Found {len(files)} downloadable files in folder", "INFO")
            return True

        except Exception as e:
            self.errors.append(f"Download capability test failed: {str(e)}")
            self.log(f"Download capability test failed: {str(e)}", "ERROR")
            return False

    def run_quick_tests(self) -> bool:
        """Run quick tests (credentials + authentication only)."""
        self.log("\n" + "="*60, "INFO")
        self.log("QUICK TEST MODE - Google Drive Connection", "INFO")
        self.log("="*60 + "\n", "INFO")

        tests = [
            ("Credentials File Check", self.test_credentials_exist),
            ("Authentication", self.test_authentication),
            ("API Connection", self.test_api_connection),
        ]

        for test_name, test_func in tests:
            self.log(f"\n--- {test_name} ---", "INFO")
            result = test_func()
            self.results[test_name] = result

        return all(self.results.values())

    def run_full_tests(self, folder_id: Optional[str] = None, test_download: bool = False) -> bool:
        """Run comprehensive tests including folder operations."""
        self.log("\n" + "="*60, "INFO")
        self.log("FULL TEST MODE - Google Drive Connection", "INFO")
        self.log("="*60 + "\n", "INFO")

        tests = [
            ("Credentials File Check", lambda: self.test_credentials_exist()),
            ("Authentication", lambda: self.test_authentication()),
            ("API Connection", lambda: self.test_api_connection()),
            ("Folder Listing", lambda: self.test_folder_listing(folder_id)),
        ]

        if test_download:
            tests.append(("Download Capability", lambda: self.test_download_capability(folder_id)))

        for test_name, test_func in tests:
            self.log(f"\n--- {test_name} ---", "INFO")
            result = test_func()
            self.results[test_name] = result

        return all(self.results.values())

    def print_summary(self):
        """Print test summary and results."""
        self.log("\n" + "="*60, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("="*60 + "\n", "INFO")

        passed = sum(1 for r in self.results.values() if r)
        total = len(self.results)

        for test_name, result in self.results.items():
            status = "PASS" if result else "FAIL"
            level = "SUCCESS" if result else "ERROR"
            self.log(f"{test_name}: {status}", level)

        self.log(f"\nTotal: {passed}/{total} tests passed", "INFO")

        if self.errors:
            self.log("\nErrors encountered:", "ERROR")
            for error in self.errors:
                self.log(f"  - {error}", "ERROR")

        if passed == total:
            self.log("\n🎉 All tests passed! Google Drive connection is working.", "SUCCESS")
            return True
        else:
            self.log(f"\n⚠️  {total - passed} test(s) failed. Please review errors above.", "ERROR")
            return False


def main():
    """Main entry point for Google Drive connection test script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Test Google Drive API connection for CRO Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/test_google_drive.py --mode quick
  python3 scripts/test_google_drive.py --mode full --folder-id 1ABC123xyz
  python3 scripts/test_google_drive.py --service-account --mode full
  python3 scripts/test_google_drive.py --mode full --folder-id 1ABC123xyz --test-download
        """
    )

    parser.add_argument(
        "--mode",
        choices=["quick", "full"],
        default="quick",
        help="Test mode: quick (credentials + auth only) or full (includes folder operations)"
    )

    parser.add_argument(
        "--service-account",
        action="store_true",
        help="Use service account authentication instead of OAuth2"
    )

    parser.add_argument(
        "--folder-id",
        type=str,
        help="Google Drive folder ID to test with (required for full mode folder operations)"
    )

    parser.add_argument(
        "--test-download",
        action="store_true",
        help="Test download capability (dry run, doesn't actually download files)"
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress detailed output, only show summary"
    )

    args = parser.parse_args()

    # Create tester
    tester = GoogleDriveConnectionTest(
        verbose=not args.quiet,
        use_service_account=args.service_account
    )

    # Run tests
    if args.mode == "quick":
        success = tester.run_quick_tests()
    else:
        success = tester.run_full_tests(
            folder_id=args.folder_id,
            test_download=args.test_download
        )

    # Print summary
    tester.print_summary()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
