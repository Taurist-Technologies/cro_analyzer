"""
Google Drive Client for CRO Analyzer

Handles authentication and document download from Google Drive.
Supports both service account and OAuth2 authentication methods.
"""

import os
import io
from pathlib import Path
from typing import List, Dict, Optional
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pickle


# If modifying these scopes, delete the file token.pickle
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class GoogleDriveClient:
    """
    Client for interacting with Google Drive API.

    Supports two authentication methods:
    1. Service Account (for server-to-server apps)
    2. OAuth2 User Credentials (for user-authorized apps)
    """

    def __init__(
        self, credentials_path: Optional[str] = None, use_service_account: bool = False
    ):
        """
        Initialize Google Drive client.

        Args:
            credentials_path: Path to credentials file
                - For service account: path to service_account.json
                - For OAuth2: path to credentials.json
            use_service_account: If True, use service account auth. Otherwise, use OAuth2.
        """
        self.credentials_path = credentials_path or os.getenv(
            "GOOGLE_CREDENTIALS_PATH", "credentials.json"
        )
        self.use_service_account = use_service_account
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Google Drive API."""
        creds = None

        if self.use_service_account:
            # Service account authentication
            # Handle directory paths - find the first .json file
            credentials_file = self.credentials_path
            if os.path.isdir(credentials_file):
                json_files = list(Path(credentials_file).glob("*.json"))
                if not json_files:
                    raise FileNotFoundError(
                        f"No JSON credentials file found in directory: {credentials_file}"
                    )
                credentials_file = str(json_files[0])
                print(f"Using service account credentials: {credentials_file}")

            creds = service_account.Credentials.from_service_account_file(
                credentials_file, scopes=SCOPES
            )
        else:
            # OAuth2 user authentication
            token_pickle = "token.pickle"

            # Load saved credentials from pickle file
            if os.path.exists(token_pickle):
                with open(token_pickle, "rb") as token:
                    creds = pickle.load(token)

            # If no valid credentials, get new ones
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                # Save credentials for next run
                with open(token_pickle, "wb") as token:
                    pickle.dump(creds, token)

        self.service = build("drive", "v3", credentials=creds)
        print(f"✓ Authenticated with Google Drive API")

    def list_files_in_folder(
        self, folder_id: str, mime_type: Optional[str] = None
    ) -> List[Dict]:
        """
        List all files in a Google Drive folder.

        Args:
            folder_id: The Google Drive folder ID
            mime_type: Optional MIME type filter (e.g., 'application/vnd.google-apps.document')

        Returns:
            List of file metadata dictionaries
        """
        query = f"'{folder_id}' in parents and trashed=false"

        if mime_type:
            query += f" and mimeType='{mime_type}'"

        results = (
            self.service.files()
            .list(
                q=query,
                pageSize=1000,
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
            )
            .execute()
        )

        items = results.get("files", [])

        print(f"✓ Found {len(items)} files in folder {folder_id}")
        return items

    def download_file(
        self, file_id: str, output_path: str, export_mime_type: Optional[str] = None
    ) -> str:
        """
        Download a file from Google Drive.

        Args:
            file_id: The file's unique ID
            output_path: Local path to save the file
            export_mime_type: For Google Docs, export MIME type
                - DOCX: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                - PDF: 'application/pdf'
                - Plain text: 'text/plain'

        Returns:
            Path to downloaded file
        """
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            if export_mime_type:
                # Export Google Docs file (e.g., Google Docs → DOCX)
                request = self.service.files().export_media(
                    fileId=file_id, mimeType=export_mime_type
                )
            else:
                # Download binary file directly
                request = self.service.files().get_media(fileId=file_id)

            # Download file
            fh = io.FileIO(output_path, "wb")
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    print(f"  Download progress: {progress}%", end="\r")

            print(f"\n✓ Downloaded: {output_path}")
            return output_path

        except Exception as e:
            print(f"✗ Error downloading file {file_id}: {str(e)}")
            raise

    def download_google_doc_as_docx(self, file_id: str, output_path: str) -> str:
        """
        Download a Google Doc as a DOCX file.

        Args:
            file_id: The Google Doc's file ID
            output_path: Local path to save the DOCX file (should end in .docx)

        Returns:
            Path to downloaded DOCX file
        """
        docx_mime_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        return self.download_file(file_id, output_path, export_mime_type=docx_mime_type)

    def bulk_download_folder_as_docx(
        self, folder_id: str, output_dir: str, file_prefix: str = "audit_"
    ) -> List[str]:
        """
        Download all Google Docs in a folder as DOCX files.

        Args:
            folder_id: The Google Drive folder ID containing audits
            output_dir: Local directory to save DOCX files
            file_prefix: Prefix for downloaded filenames

        Returns:
            List of paths to downloaded DOCX files
        """
        # Get all Google Docs in folder
        google_docs_mime = "application/vnd.google-apps.document"
        files = self.list_files_in_folder(folder_id, mime_type=google_docs_mime)

        print(f"\n📥 Downloading {len(files)} Google Docs as DOCX...")

        downloaded_paths = []
        skipped_large_files = []

        for i, file in enumerate(files, 1):
            file_name = file["name"].replace(" ", "_").replace("/", "-")
            output_path = os.path.join(output_dir, f"{file_prefix}{file_name}.docx")

            print(f"\n[{i}/{len(files)}] {file['name']}")

            try:
                path = self.download_google_doc_as_docx(file["id"], output_path)
                downloaded_paths.append(path)
            except Exception as e:
                error_msg = str(e)
                # Check if it's the "file too large" error
                if (
                    "too large to be exported" in error_msg
                    or "exportSizeLimitExceeded" in error_msg
                ):
                    print(f"⚠️  Skipped (file too large): {file['name']}")
                    skipped_large_files.append(file["name"])
                else:
                    print(f"✗ Failed to download {file['name']}: {error_msg}")
                continue

        print(f"\n✓ Successfully downloaded {len(downloaded_paths)}/{len(files)} files")
        if skipped_large_files:
            print(f"⚠️  Skipped {len(skipped_large_files)} files that were too large:")
            for name in skipped_large_files[:5]:  # Show first 5
                print(f"   - {name}")
            if len(skipped_large_files) > 5:
                print(f"   ... and {len(skipped_large_files) - 5} more")
        return downloaded_paths


# Usage example
if __name__ == "__main__":
    # Example 1: Download all audits from a folder
    client = GoogleDriveClient(credentials_path="credentials.json")

    # Replace with your actual folder ID
    FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

    # Download all Google Docs as DOCX
    output_directory = "downloaded_audits"
    downloaded_files = client.bulk_download_folder_as_docx(
        folder_id=FOLDER_ID, output_dir=output_directory
    )

    print(f"\n📁 Downloaded files saved to: {output_directory}/")
    for file in downloaded_files:
        print(f"  - {file}")
