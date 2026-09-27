"""Google Drive authentication.

Uses Application Default Credentials: either a service-account key file
referenced by GOOGLE_APPLICATION_CREDENTIALS, or a user account set up with
`gcloud auth application-default login --scopes=https://www.googleapis.com/auth/drive`.
Either way the credentials must carry the scope below.
"""
from __future__ import annotations

import google.auth
from googleapiclient.discovery import build

DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']


def default_credentials():
    credentials, _ = google.auth.default(scopes=DRIVE_SCOPES)
    return credentials


def drive_service(credentials=None):
    credentials = credentials or default_credentials()
    return build('drive', 'v3', credentials=credentials, cache_discovery=False)
