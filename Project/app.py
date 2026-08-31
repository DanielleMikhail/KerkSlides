import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
import gspread
from pypdf import PdfWriter, PdfReader
from io import BytesIO


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

# Google Drive folder containing the source Google Docs
SOURCE_FOLDER_ID = "1q-5HeICSq5zBoQAEDb_PNA3iMXbgrNBn"

# Google Sheet containing the shared selection
SPREADSHEET_ID = "1f4EFf5HeWCUtPtqYtsoooOAXpibKiuXEoWU0CHAOjWQ"

# Google Drive folder where the combined PDF will be stored
#
# This may be the same folder as SOURCE_FOLDER_ID, but a separate
# output folder is cleaner.
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
# GOOGLE SERVICES
# ============================================================

drive_service = build(
    "drive",
    "v3",
    credentials=credentials,
    cache_discovery=False,
)

gc = gspread.authorize(credentials)

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

        result = drive_service.files().list(
            q=(
                f"'{SOURCE_FOLDER_ID}' in parents "
                "and mimeType='application/vnd.google-apps.document' "
                "and trashed=false"
            ),
            fields="nextPageToken, files(id, name)",
            orderBy="name",
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        files.extend(
            result.get("files", [])
        )

        page_token = result.get(
            "nextPageToken"
        )

        if not page_token:
            break

    return files


def get_shared_selection():
    """
    Read the selected status from Google Sheets.
    """

    rows = sheet.get_all_records()

    return {
        str(row["document_id"]):
            str(row["selected"]).strip().upper() == "TRUE"
        for row in rows
        if row.get("document_id")
    }


def create_combined_pdf(selected_files):
    """
    Export the selected Google Docs as PDFs and combine them.

    Returns:
        pdf_bytes
        page_details
        total_page_count
    """

    pdf_writer = PdfWriter()

    page_details = []
    total_page_count = 0

    for file in selected_files:

        request = drive_service.files().export_media(
            fileId=file["id"],
            mimeType="application/pdf",
        )

        pdf_data = request.execute()

        pdf_reader = PdfReader(
            BytesIO(pdf_data)
        )

        document_page_count = len(
            pdf_reader.pages
        )

        page_details.append({
            "name": file["name"],
            "pages": document_page_count,
        })

        total_page_count += document_page_count

        for page in pdf_reader.pages:
            pdf_writer.add_page(page)

    combined_pdf = BytesIO()

    pdf_writer.write(combined_pdf)
    pdf_writer.close()

    combined_pdf.seek(0)

    pdf_bytes = combined_pdf.getvalue()

    # Verify the final number of pages
    verification_reader = PdfReader(
        BytesIO(pdf_bytes)
    )

    verified_page_count = len(
        verification_reader.pages
    )

    if verified_page_count != total_page_count:

        raise ValueError(
            "The number of pages in the combined PDF does not "
            "match the total number of exported pages."
        )

    return (
        pdf_bytes,
        page_details,
        verified_page_count,
    )


def find_existing_output_pdf():
    """
    Find the existing compiled PDF in the output folder.
    """

    escaped_file_name = (
        OUTPUT_FILE_NAME
        .replace("\\", "\\\\")
        .replace("'", "\\'")
    )

    query = (
        f"'{OUTPUT_FOLDER_ID}' in parents "
        f"and name='{escaped_file_name}' "
        "and mimeType='application/pdf' "
        "and trashed=false"
    )

    result = drive_service.files().list(
        q=query,
        fields="files(id, name)",
        pageSize=10,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()

    files = result.get("files", [])

    if files:
        return files[0]

    return None


def enable_link_access(file_id):
    """
    Give anyone with the link permission to view the PDF.

    If public sharing is disabled in Google Workspace,
    this function returns the error without stopping the app.
    """

    try:

        permissions = drive_service.permissions().list(
            fileId=file_id,
            fields="permissions(id, type, role)",
            supportsAllDrives=True,
        ).execute()

        anyone_permission_exists = any(
            permission.get("type") == "anyone"
            and permission.get("role") == "reader"
            for permission in permissions.get(
                "permissions",
                [],
            )
        )

        if not anyone_permission_exists:

            drive_service.permissions().create(
                fileId=file_id,
                body={
                    "type": "anyone",
                    "role": "reader",
                },
                fields="id",
                supportsAllDrives=True,
            ).execute()

        return None

    except HttpError as error:

        return str(error)


def upload_or_update_pdf(pdf_bytes):
    """
    Upload the compiled PDF to Google Drive.

    If the file already exists, replace its contents.
    This means that the Google Drive URL remains stable.
    """

    existing_file = find_existing_output_pdf()

    pdf_stream = BytesIO(pdf_bytes)

    media = MediaIoBaseUpload(
        pdf_stream,
        mimetype="application/pdf",
        resumable=True,
    )

    if existing_file:

        uploaded_file = drive_service.files().update(
            fileId=existing_file["id"],
            media_body=media,
            fields="id, name",
            supportsAllDrives=True,
        ).execute()

    else:

        file_metadata = {
            "name": OUTPUT_FILE_NAME,
            "mimeType": "application/pdf",
            "parents": [OUTPUT_FOLDER_ID],
        }

        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name",
            supportsAllDrives=True,
        ).execute()

    file_id = uploaded_file["id"]

    permission_error = enable_link_access(
        file_id
    )

    # Google Drive preview page
    preview_url = (
        f"https://drive.google.com/file/d/"
        f"{file_id}/view"
    )

    # Direct PDF response
    direct_url = (
        f"https://drive.google.com/uc?"
        f"export=download&id={file_id}"
    )

    return {
        "file_id": file_id,
        "preview_url": preview_url,
        "direct_url": direct_url,
        "permission_error": permission_error,
    }


# ============================================================
# LOAD GOOGLE DOCS
# ============================================================

try:

    google_docs = get_google_docs()

except HttpError as error:

    st.error(
        "The app could not access the Google Drive folder. "
        "Check the folder ID and service account permissions."
    )

    st.exception(error)
    st.stop()


# ============================================================
# CREATE TABS
# ============================================================

tab_select, tab_slides = st.tabs(
    [
        "📁 Select documents",
        "📖 Open slides",
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
                "The shared selection could not be read "
                "from Google Sheets."
            )

            st.exception(error)
            st.stop()

        current_selection = []

        # ----------------------------------------------------
        # DOCUMENT CHECKBOXES
        # ----------------------------------------------------

        for file in google_docs:

            selected = st.checkbox(
                file["name"],
                value=shared_selection.get(
                    file["id"],
                    False,
                ),
                key=f"checkbox_{file['id']}",
            )

            if selected:

                current_selection.append(
                    file["id"]
                )

        # ----------------------------------------------------
        # UPDATE SHARED SELECTION
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

                updates = []

                for file in google_docs:

                    row_number = row_by_id.get(
                        file["id"]
                    )

                    if row_number is None:
                        continue

                    if file["id"] in current_selection:
                        selected_value = "TRUE"
                    else:
                        selected_value = "FALSE"

                    updates.append({
                        "range": f"C{row_number}",
                        "values": [[selected_value]],
                    })

                if updates:

                    sheet.batch_update(
                        updates
                    )

                # Remove the previous compiled file from this
                # user's session because the selection changed.
                st.session_state.pop(
                    "compiled_pdf_bytes",
                    None,
                )

                st.session_state.pop(
                    "compiled_preview_url",
                    None,
                )

                st.session_state.pop(
                    "compiled_direct_url",
                    None,
                )

                st.session_state.pop(
                    "compiled_page_count",
                    None,
                )

                st.session_state.pop(
                    "compiled_page_details",
                    None,
                )

                st.success(
                    "Shared selection updated."
                )

                st.rerun()

            except Exception as error:

                st.error(
                    "The shared selection could not be updated."
                )

                st.exception(error)


# ============================================================
# TAB 2: CREATE AND OPEN SLIDES
# ============================================================

with tab_slides:

    st.header("📖 Combined slides")

    try:

        shared_selection = get_shared_selection()

    except Exception as error:

        st.error(
            "The shared selection could not be read "
            "from Google Sheets."
        )

        st.exception(error)
        st.stop()

    selected_files = [
        file
        for file in google_docs
        if shared_selection.get(
            file["id"],
            False,
        )
    ]

    if not selected_files:

        st.info(
            "No documents have been selected yet. "
            "Select documents in the first tab."
        )

    else:

        st.write(
            f"**{len(selected_files)} documents selected.**"
        )

        with st.expander(
            "View selected documents"
        ):

            for file in selected_files:
                st.write(f"• {file['name']}")

        st.divider()

        # ----------------------------------------------------
        # CREATE BUTTON
        # ----------------------------------------------------

        if st.button(
            "🔄 Create combined slides",
            type="primary",
            use_container_width=True,
        ):

            try:

                with st.spinner(
                    "Exporting and combining documents..."
                ):

                    (
                        pdf_bytes,
                        page_details,
                        verified_page_count,
                    ) = create_combined_pdf(
                        selected_files
                    )

                with st.spinner(
                    "Uploading the PDF to Google Drive..."
                ):

                    upload_result = upload_or_update_pdf(
                        pdf_bytes
                    )

                st.session_state[
                    "compiled_pdf_bytes"
                ] = pdf_bytes

                st.session_state[
                    "compiled_preview_url"
                ] = upload_result["preview_url"]

                st.session_state[
                    "compiled_direct_url"
                ] = upload_result["direct_url"]

                st.session_state[
                    "compiled_page_count"
                ] = verified_page_count

                st.session_state[
                    "compiled_page_details"
                ] = page_details

                st.session_state[
                    "permission_error"
                ] = upload_result["permission_error"]

                st.success(
                    "The combined slides are ready."
                )

            except HttpError as error:

                st.error(
                    "Google Drive could not create or update "
                    "the combined PDF."
                )

                st.exception(error)

            except Exception as error:

                st.error(
                    "The combined PDF could not be created."
                )

                st.exception(error)

        # ----------------------------------------------------
        # RESULTS
        # ----------------------------------------------------

        if st.session_state.get(
            "compiled_preview_url"
        ):

            st.divider()

            # Debug information requested
            page_count = st.session_state.get(
                "compiled_page_count",
                0,
            )

            st.success(
                f"Combined PDF pages: {page_count}"
            )

            page_details = st.session_state.get(
                "compiled_page_details",
                [],
            )

            with st.expander(
                "Check the number of pages per document"
            ):

                for document in page_details:

                    st.write(
                        f"• {document['name']}: "
                        f"{document['pages']} page(s)"
                    )

            # This button opens Google Drive in a new browser tab
            st.link_button(
                "⛶ Open slides in new window",
                st.session_state[
                    "compiled_preview_url"
                ],
                type="primary",
                use_container_width=True,
            )

            st.caption(
                "On iPhone or iPad, tap the button above. "
                "The PDF should open in a separate Google Drive "
                "viewer page. Scroll vertically to view all pages."
            )

            # Direct download option
            if st.session_state.get(
                "compiled_pdf_bytes"
            ):

                st.download_button(
                    "⬇️ Download combined PDF",
                    data=st.session_state[
                        "compiled_pdf_bytes"
                    ],
                    file_name=OUTPUT_FILE_NAME,
                    mime="application/pdf",
                    use_container_width=True,
                )

            # Public-sharing problem
            if st.session_state.get(
                "permission_error"
            ):

                st.warning(
                    "The PDF was created, but public link access "
                    "could not be enabled. Your Google Workspace "
                    "administrator may block public sharing. "
                    "Visitors will need Google Drive access."
                )

                with st.expander(
                    "Technical sharing error"
                ):

                    st.code(
                        st.session_state[
                            "permission_error"
                        ]
                    )
