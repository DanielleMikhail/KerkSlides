import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
import gspread
from pypdf import PdfWriter, PdfReader
from io import BytesIO
import base64
import streamlit.components.v1 as components



# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="KerkSlides",
    page_icon="⛪",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("⛪ KerkSlides")


# ============================================================
# CONFIGURATION
# ============================================================

# Folder containing the source Google Docs
SOURCE_FOLDER_ID = "1q-5HeICSq5zBoQAEDb_PNA3iMXbgrNBn"

# Google Sheet containing:
# document_id | document_name | selected
SPREADSHEET_ID = "1f4EFf5HeWCUtPtqYtsoooOAXpibKiuXEoWU0CHAOjWQ"

# Folder in which the compiled PDF will be saved
#
# You can use the same folder as SOURCE_FOLDER_ID or create
# a separate folder called, for example, KerkSlides_Output.
OUTPUT_FOLDER_ID = "1-gSEGSv3aawp1JQ9ou7gy50ihPGCc0N3"

OUTPUT_FILE_NAME = "KerkSlides_Compiled.pdf"


# ============================================================
# GOOGLE CREDENTIALS
# ============================================================

credentials = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ],
)


# ============================================================
# GOOGLE DRIVE
# ============================================================

drive_service = build(
    "drive",
    "v3",
    credentials=credentials,
    cache_discovery=False,
)


# ============================================================
# GOOGLE SHEETS
# ============================================================

gc = gspread.authorize(credentials)

sheet = gc.open_by_key(
    SPREADSHEET_ID
).sheet1


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def escape_drive_query(value):
    """
    Escape a text value before inserting it into a Drive query.
    """
    return value.replace("\\", "\\\\").replace("'", "\\'")


def get_google_docs():
    """
    Retrieve all Google Docs from the configured source folder.
    Handles pagination if the folder contains many files.
    """

    files = []
    page_token = None

    while True:

        results = drive_service.files().list(
            q=(
                f"'{SOURCE_FOLDER_ID}' in parents "
                "and mimeType='application/vnd.google-apps.document' "
                "and trashed=false"
            ),
            fields="nextPageToken, files(id, name)",
            orderBy="name",
            pageToken=page_token,
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        files.extend(results.get("files", []))

        page_token = results.get("nextPageToken")

        if not page_token:
            break

    return files


def get_shared_selection():
    """
    Read the currently selected documents from Google Sheets.
    """

    rows = sheet.get_all_records()

    return {
        str(row["document_id"]):
            str(row["selected"]).strip().upper() == "TRUE"
        
)

 
