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
        for row in rows
        if row.get("document_id")
    }

# ============================================================
# GET GOOGLE DOCS
# ============================================================

try:
    google_docs = get_google_docs()

except Exception as error:
    st.error("Could not load the Google Docs.")
    st.exception(error)
    st.stop()


# ============================================================
# CREATE TABS
# ============================================================

tab_select, tab_preview = st.tabs(
    [
        "📁 Select documents",
        "👀 Preview",
    ]
)


# ============================================================
# TAB 1: SELECT DOCUMENTS
# ============================================================

with tab_select:

    st.header("Select documents")

    if not google_docs:

        st.warning(
            "No Google Docs were found in the source folder."
        )

    else:

        st.write(
            f"Found **{len(google_docs)} documents**."
        )

        try:
            shared_selection = get_shared_selection()

        except Exception as error:
            st.error(
                "Could not read the current selection "
                "from Google Sheets."
            )
            st.exception(error)
            st.stop()

        current_selection = []

        # ----------------------------------------------------
        # DOCUMENT CHECKBOXES
        # ----------------------------------------------------

        for file in google_docs:

            document_id = str(file["id"])

            selected = st.checkbox(
                file["name"],
                value=shared_selection.get(
                    document_id,
                    False,
                ),
                key=f"checkbox_{document_id}",
            )

            if selected:
                current_selection.append(
                    document_id
                )

        # ----------------------------------------------------
        # UPDATE GOOGLE SHEET
        # ----------------------------------------------------

        st.divider()

        if st.button(
            "💾 Update shared selection",
            type="primary",
            use_container_width=True,
        ):

            try:

                rows = sheet.get_all_records()

                row_by_id = {
                    str(row["document_id"]): index + 2
                    for index, row in enumerate(rows)
                    if row.get("document_id")
                }

                for file in google_docs:

                    document_id = str(file["id"])

                    row_number = row_by_id.get(
                        document_id
                    )

                    selected_value = (
                        "TRUE"
                        if document_id in current_selection
                        else "FALSE"
                    )

                    if row_number:

                        # Update existing row
                        sheet.update_cell(
                            row_number,
                            2,
                            file["name"],
                        )

                        sheet.update_cell(
                            row_number,
                            3,
                            selected_value,
                        )

                    else:

                        # Add new document to the sheet
                        sheet.append_row(
                            [
                                document_id,
                                file["name"],
                                selected_value,
                            ],
                            value_input_option="USER_ENTERED",
                        )

                st.success(
                    "Shared selection updated! ✅"
                )

                st.rerun()

            except Exception as error:

                st.error(
                    "Could not update the shared selection."
                )

                st.exception(error)


# ============================================================
# TAB 2: PREVIEW
# ============================================================

with tab_preview:

    st.header("👀 Combined document")

    try:
        shared_selection = get_shared_selection()

    except Exception as error:
        st.error(
            "Could not read the current selection "
            "from Google Sheets."
        )
        st.exception(error)
        st.stop()

    selected_files = [
        file
        for file in google_docs
        if shared_selection.get(
            str(file["id"]),
            False,
        )
    ]

    if not selected_files:

        st.info(
            "No documents have been selected yet. "
            "Select documents in the first tab and click "
            "'Update shared selection'."
        )

    else:

        st.write(
            f"**{len(selected_files)} documents** selected."
        )

        with st.expander(
            "View selected documents"
        ):

            for index, file in enumerate(
                selected_files,
                start=1,
            ):
                st.write(
                    f"{index}. {file['name']}"
                )

        # ----------------------------------------------------
        # COMPILE PDF
        # ----------------------------------------------------

        pdf_writer = PdfWriter()

        with st.spinner(
            "Creating combined document..."
        ):

            try:

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
                        pdf_writer.add_page(page)

            except Exception as error:

                st.error(
                    "Could not export and combine "
                    "the selected documents."
                )

                st.exception(error)
                st.stop()

        # ----------------------------------------------------
        # CREATE PDF BYTES
        # ----------------------------------------------------

        combined_pdf = BytesIO()

        pdf_writer.write(
            combined_pdf
        )

        combined_pdf.seek(0)

        pdf_bytes = combined_pdf.getvalue()

        # ----------------------------------------------------
        # DOWNLOAD BUTTON
        # ----------------------------------------------------

        st.download_button(
            "⬇️ Download combined PDF",
            data=pdf_bytes,
            file_name=OUTPUT_FILE_NAME,
            mime="application/pdf",
            use_container_width=True,
        )

        st.divider()

        st.subheader(
            "📖 Document preview"
        )

        # ----------------------------------------------------
        # SIMPLE PDF PREVIEW
        # ----------------------------------------------------

        pdf_base64 = base64.b64encode(
            pdf_bytes
        ).decode("utf-8")

        preview_html = f"""
        data:application/pdf;base64,{pdf_base64}</iframe>
        """

        components.html(
            preview_html,
            height=770,
            scrolling=False,
        )
 
