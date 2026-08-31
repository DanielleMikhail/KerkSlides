import base64
from io import BytesIO

import gspread
import streamlit as st
import streamlit.components.v1 as components

from google.oauth2 import service_account
from googleapiclient.discovery import build
from pypdf import PdfReader, PdfWriter


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

# Name used when downloading the compiled PDF
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

def get_google_docs():
    """
    Retrieve all Google Docs from the configured source folder.
    Handles pagination when the folder contains many files.
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

    st.error(
        "Could not load the Google Docs."
    )

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

    st.header(
        "Select documents"
    )

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

            document_id = str(
                file["id"]
            )

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

                    document_id = str(
                        file["id"]
                    )

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

                        # Add new document to Google Sheets
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

    st.header(
        "👀 Combined document"
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

                        pdf_writer.add_page(
                            page
                        )

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

        st.caption(
            "On iPhone or iPad, use the button below to open "
            "the document in a separate full-page Safari tab."
        )

        # ----------------------------------------------------
        # CONVERT PDF TO BASE64
        # ----------------------------------------------------

        pdf_base64 = base64.b64encode(
            pdf_bytes
        ).decode("utf-8")

        # ----------------------------------------------------
        # STANDALONE PDF VIEWER
        # ----------------------------------------------------

        preview_html = f"""
<!DOCTYPE html>

<html>

<head>

    <meta
        name="viewport"
        content="
            width=device-width,
            initial-scale=1.0,
            viewport-fit=cover
        "
    >

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
            background: #525659;
            font-family:
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;
        }}

        #viewer-container {{
            display: flex;
            flex-direction: column;
            width: 100%;
            height: 100vh;
            height: 100dvh;
            background: #525659;
        }}

        #toolbar {{
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 58px;
            padding:
                max(8px, env(safe-area-inset-top))
                max(10px, env(safe-area-inset-right))
                8px
                max(10px, env(safe-area-inset-left));
            background: #242629;
        }}

        #open-button {{
            width: 100%;
            max-width: 520px;
            min-height: 42px;
            border: none;
            border-radius: 8px;
            padding: 10px 18px;
            background: #ffffff;
            color: #1f1f1f;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
        }}

        #open-button:active {{
            transform: scale(0.98);
            background: #eeeeee;
        }}

        #pdf-frame {{
            flex: 1;
            display: block;
            width: 100%;
            height: 100%;
            border: none;
            background: #525659;
        }}

        #message {{
            display: none;
            padding: 14px;
            background: #fff3cd;
            color: #664d03;
            text-align: center;
            font-size: 14px;
        }}

        @media (max-width: 600px) {{

            #toolbar {{
                min-height: 54px;
            }}

            #open-button {{
                min-height: 40px;
                font-size: 15px;
            }}

        }}

    </style>

</head>

<body>

    <div id="viewer-container">

        <div id="toolbar">

            <button
                id="open-button"
                type="button"
                onclick="openStandaloneViewer()"
            >
                ⛶ Open full-screen PDF
            </button>

        </div>

        <div id="message"></div>

        <iframe
            id="pdf-frame"
            title="KerkSlides PDF preview"
        ></iframe>

    </div>

    <script>

        const pdfBase64 = "{pdf_base64}";

        let pdfBlobUrl = null;


        /*
        Convert the Python Base64 text back into a PDF file
        inside the browser.
        */

        function createPdfBlobUrl() {{

            if (pdfBlobUrl) {{
                return pdfBlobUrl;
            }}

            const binaryString =
                window.atob(pdfBase64);

            const byteArray =
                new Uint8Array(binaryString.length);

            for (
                let index = 0;
                index < binaryString.length;
                index++
            ) {{

                byteArray[index] =
                    binaryString.charCodeAt(index);

            }}

            const pdfBlob = new Blob(
                [byteArray],
                {{
                    type: "application/pdf"
                }}
            );

            pdfBlobUrl =
                URL.createObjectURL(pdfBlob);

            return pdfBlobUrl;

        }}


        /*
        Show the PDF inside the Streamlit preview.
        */

        function loadEmbeddedPreview() {{

            const pdfUrl =
                createPdfBlobUrl();

            document.getElementById(
                "pdf-frame"
            ).src = pdfUrl;

        }}


        /*
        Open the PDF in a separate browser tab.

        On an iPhone or iPad, Safari then uses its own PDF
        viewer. The PDF is no longer restricted to the
        small Streamlit preview frame.
        */

        function openStandaloneViewer() {{

            const message =
                document.getElementById("message");

            message.style.display = "none";

            /*
            Open the tab immediately from the button click.
            This helps prevent Safari's popup blocker from
            blocking the new tab.
            */

            const newTab =
                window.open("", "_blank");

            if (!newTab) {{

                message.innerHTML =
                    "Safari blocked the new tab. " +
                    "Please allow pop-ups for this website " +
                    "and press the button again.";

                message.style.display = "block";

                return;

            }}

            try {{

                newTab.document.write(`
                    <!DOCTYPE html>

                    <html>

                    <head>

                        <meta
                            name="viewport"
                            content="
                                width=device-width,
                                initial-scale=1.0,
                                viewport-fit=cover
                            "
                        >

                        <title>KerkSlides</title>

                        <style>

                            html,
                            body {{
                                width: 100%;
                                height: 100%;
                                margin: 0;
                                padding: 0;
                                overflow: hidden;
                                background: #525659;
                            }}

                            iframe {{
                                display: block;
                                width: 100%;
                                height: 100vh;
                                height: 100dvh;
                                border: none;
                            }}

                        </style>

                    </head>

                    <body>

                        <iframe
                            id="standalone-pdf"
                            title="KerkSlides PDF"
                        ></iframe>

                    </body>

                    </html>
                `);

                newTab.document.close();

                const pdfUrl =
                    createPdfBlobUrl();

                newTab.document.getElementById(
                    "standalone-pdf"
                ).src = pdfUrl;

            }} catch (error) {{

                console.error(
                    "Could not create standalone viewer:",
                    error
                );

                newTab.close();

                message.innerHTML =
                    "The PDF could not be opened in a new tab. " +
                    "Please use the download button above.";

                message.style.display = "block";

            }}

        }}


        /*
        Load the normal preview when the Streamlit component
        starts.
        */

        loadEmbeddedPreview();

    </script>

</body>

</html>
"""

        # ----------------------------------------------------
        # DISPLAY PDF VIEWER
        # ----------------------------------------------------

        components.html(
            preview_html,
            height=800,
            scrolling=False,
        )
