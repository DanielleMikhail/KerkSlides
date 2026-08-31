import base64
from io import BytesIO

import gspread
import streamlit as st
import streamlit.components.v1 as components

from google.oauth2 import service_account
from googleapiclient.discovery import build
from pypdf import PdfReader, PdfWriter


# ============================================================
# APP MODE
# ============================================================

# Normal app:
# https://your-app.streamlit.app
#
# Presentation:
# https://your-app.streamlit.app/?view=presentation

presentation_mode = (
    st.query_params.get("view", "")
    == "presentation"
)


# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title=(
        "KerkSlides Presentation"
        if presentation_mode
        else "KerkSlides"
    ),
    page_icon="⛪",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# PRESENTATION PAGE STYLING
# ============================================================

if presentation_mode:

    st.markdown(
        """
        <style>

            #MainMenu {
                display: none;
            }

            header {
                display: none;
            }

            footer {
                display: none;
            }

            [data-testid="stToolbar"] {
                display: none;
            }

            [data-testid="stDecoration"] {
                display: none;
            }

            [data-testid="stStatusWidget"] {
                display: none;
            }

            [data-testid="stSidebar"] {
                display: none;
            }

            [data-testid="collapsedControl"] {
                display: none;
            }

            .stApp {
                background: #202124;
            }

            .block-container {
                max-width: 100%;
                padding: 0;
                margin: 0;
            }

            iframe {
                display: block;
                border: none;
            }

        </style>
        """,
        unsafe_allow_html=True,
    )

else:

    st.title("⛪ KerkSlides")


# ============================================================
# CONFIGURATION
# ============================================================

# Folder containing the source Google Docs
SOURCE_FOLDER_ID = "1q-5HeICSq5zBoQAEDb_PNA3iMXbgrNBn"

# Google Sheet containing:
# document_id | document_name | selected
SPREADSHEET_ID = "1f4EFf5HeWCUtPtqYtsoooOAXpibKiuXEoWU0CHAOjWQ"

# Name used when downloading the combined PDF
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

gc = gspread.authorize(
    credentials
)

sheet = gc.open_by_key(
    SPREADSHEET_ID
).sheet1


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_google_docs():
    """
    Retrieve all Google Docs from the source folder.
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
            fields=(
                "nextPageToken, "
                "files(id, name)"
            ),
            orderBy="name",
            pageToken=page_token,
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        files.extend(
            results.get("files", [])
        )

        page_token = results.get(
            "nextPageToken"
        )

        if not page_token:
            break

    return files


def get_shared_selection():
    """
    Read the currently selected documents from Google Sheets.
    """

    rows = sheet.get_all_records()

    return {
        str(row["document_id"]): (
            str(row.get("selected", ""))
            .strip()
            .upper()
            == "TRUE"
        )
        for row in rows
        if row.get("document_id")
    }


def save_shared_selection(
    google_docs,
    current_selection,
):
    """
    Update existing Google Sheet rows and append new documents.
    """

    rows = sheet.get_all_records()

    row_by_id = {
        str(row["document_id"]): index + 2
        for index, row in enumerate(rows)
        if row.get("document_id")
    }

    current_selection = set(
        current_selection
    )

    values_to_append = []

    for file in google_docs:

        document_id = str(
            file["id"]
        )

        document_name = file["name"]

        selected_value = (
            "TRUE"
            if document_id in current_selection
            else "FALSE"
        )

        row_number = row_by_id.get(
            document_id
        )

        if row_number:

            sheet.update(
                range_name=f"B{row_number}:C{row_number}",
                values=[
                    [
                        document_name,
                        selected_value,
                    ]
                ],
            )

        else:

            values_to_append.append(
                [
                    document_id,
                    document_name,
                    selected_value,
                ]
            )

    if values_to_append:

        sheet.append_rows(
            values_to_append,
            value_input_option="USER_ENTERED",
        )


def get_selected_files(
    google_docs,
    shared_selection,
):
    """
    Return only the documents selected in Google Sheets.
    """

    return [
        file
        for file in google_docs
        if shared_selection.get(
            str(file["id"]),
            False,
        )
    ]


def compile_selected_pdf(
    selected_files,
):
    """
    Export selected Google Docs and combine them into one PDF.
    """

    pdf_writer = PdfWriter()

    for file in selected_files:

        request = (
            drive_service.files().export_media(
                fileId=file["id"],
                mimeType="application/pdf",
            )
        )

        pdf_data = request.execute()

        pdf_reader = PdfReader(
            BytesIO(pdf_data)
        )

        for page in pdf_reader.pages:

            pdf_writer.add_page(
                page
            )

    combined_pdf = BytesIO()

    pdf_writer.write(
        combined_pdf
    )

    combined_pdf.seek(0)

    return combined_pdf.getvalue()


def create_pdf_viewer(
    pdf_bytes,
):
    """
    Create the PDF.js viewer.

    The viewer displays one page at a time and supports:
    - previous and next buttons
    - swipe navigation
    - zoom
    - fit-to-screen
    - fullscreen where supported
    """

    pdf_base64 = base64.b64encode(
        pdf_bytes
    ).decode("utf-8")

    viewer_html = f"""
<!DOCTYPE html>

<html lang="en">

<head>

    <meta
        name="viewport"
        content="
            width=device-width,
            initial-scale=1.0,
            maximum-scale=5.0,
            user-scalable=yes,
            viewport-fit=cover
        "
    >

    <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>

    <style>

        * {{
            box-sizing: border-box;
        }}

        html,
        body {{
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: #202124;
            font-family:
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;
        }}

        #viewer {{
            position: fixed;
            inset: 0;
            width: 100vw;
            height: 100vh;
            height: 100dvh;
            display: flex;
            flex-direction: column;
            background: #202124;
        }}

        #toolbar {{
            flex: 0 0 auto;
            min-height: 54px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding:
                max(6px, env(safe-area-inset-top))
                max(8px, env(safe-area-inset-right))
                6px
                max(8px, env(safe-area-inset-left));
            background: #292b2d;
            z-index: 20;
        }}

        button {{
            min-width: 42px;
            min-height: 38px;
            border: none;
            border-radius: 8px;
            padding: 8px 11px;
            background: white;
            color: #202124;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            touch-action: manipulation;
        }}

        button:active {{
            transform: scale(0.96);
            background: #e8eaed;
        }}

        button:disabled {{
            opacity: 0.4;
            cursor: default;
        }}

        #page-info {{
            min-width: 72px;
            color: white;
            text-align: center;
            font-size: 14px;
            white-space: nowrap;
        }}

        #pdf-container {{
            flex: 1 1 auto;
            min-height: 0;
            width: 100%;
            overflow: auto;
            -webkit-overflow-scrolling: touch;
            overscroll-behavior: contain;
            padding:
                8px
                max(5px, env(safe-area-inset-right))
                max(8px, env(safe-area-inset-bottom))
                max(5px, env(safe-area-inset-left));
            background: #525659;
            text-align: center;
        }}

        #pdf-canvas {{
            display: none;
            margin: 0 auto;
            background: white;
            box-shadow:
                0 3px 14px
                rgba(0, 0, 0, 0.45);
        }}

        #loading {{
            padding: 40px 20px;
            color: white;
            text-align: center;
            font-size: 16px;
        }}

        #error {{
            display: none;
            margin: 20px;
            padding: 15px;
            border-radius: 8px;
            background: #b3261e;
            color: white;
            text-align: center;
        }}

        #viewer:fullscreen {{
            width: 100vw;
            height: 100vh;
        }}

        #viewer:-webkit-full-screen {{
            width: 100vw;
            height: 100vh;
        }}

        @media (max-width: 600px) {{

            #toolbar {{
                min-height: 50px;
                
