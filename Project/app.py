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
        # DEBUG

        combined_reader = PdfReader(
            BytesIO(pdf_bytes)
        )
        
        st.write(
            f"Combined PDF pages: {len(combined_reader.pages)}"
        )

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

        st.subheader(
    "📖 Document preview"
)

# ----------------------------------------------------
# CONVERT PDF TO BASE64
# ----------------------------------------------------

pdf_base64 = base64.b64encode(
    pdf_bytes
).decode("utf-8")


# ----------------------------------------------------
# PDF.JS VIEWER
# ----------------------------------------------------

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
            background: #525659;
            font-family:
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;
        }}

        #viewer {{
            position: fixed;
            inset: 0;
            width: 100%;
            height: 100vh;
            height: 100dvh;
            display: flex;
            flex-direction: column;
            background: #525659;
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
            z-index: 10;
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
        }}

        button:disabled {{
            opacity: 0.4;
        }}

        #page-info {{
            min-width: 70px;
            color: white;
            text-align: center;
            font-size: 14px;
        }}

        #pdf-container {{
            flex: 1 1 auto;
            min-height: 0;
            width: 100%;
            overflow: auto;
            -webkit-overflow-scrolling: touch;
            padding:
                10px
                max(5px, env(safe-area-inset-right))
                max(10px, env(safe-area-inset-bottom))
                max(5px, env(safe-area-inset-left));
            background: #525659;
            text-align: center;
        }}

        #pdf-canvas {{
            display: none;
            margin: 0 auto;
            background: white;
            box-shadow: 0 3px 14px rgba(0, 0, 0, 0.45);
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

        @media (max-width: 600px) {{

            #toolbar {{
                min-height: 50px;
                gap: 4px;
            }}

            button {{
                min-width: 37px;
                min-height: 36px;
                padding: 7px 8px;
                font-size: 13px;
            }}

            #page-info {{
                min-width: 60px;
                font-size: 12px;
            }}

            #pdf-container {{
                padding-top: 5px;
            }}

        }}

    </style>

</head>

<body>

    <div id="viewer">

        <div id="toolbar">

            <button
                id="previous-button"
                onclick="previousPage()"
            >
                ◀
            </button>

            <span id="page-info">
                Loading...
            </span>

            <button
                id="next-button"
                onclick="nextPage()"
            >
                ▶
            </button>

            <button onclick="zoomOut()">
                −
            </button>

            <button onclick="fitPage()">
                Fit
            </button>

            <button onclick="zoomIn()">
                +
            </button>

        </div>

        <div id="pdf-container">

            <div id="loading">
                Loading document...
            </div>

            <div id="error">
                The document could not be loaded.
            </div>

            <canvas id="pdf-canvas"></canvas>

        </div>

    </div>

    <script>

        pdfjsLib.GlobalWorkerOptions.workerSrc =
            "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";


        const pdfBase64 = "{pdf_base64}";

        const pdfData = Uint8Array.from(
            window.atob(pdfBase64),
            character => character.charCodeAt(0)
        );


        let pdfDocument = null;
        let currentPage = 1;
        let zoomFactor = 1.0;
        let fitScale = 1.0;
        let rendering = false;


        const container =
            document.getElementById("pdf-container");

        const canvas =
            document.getElementById("pdf-canvas");

        const context =
            canvas.getContext("2d");

        const pageInfo =
            document.getElementById("page-info");

        const previousButton =
            document.getElementById("previous-button");

        const nextButton =
            document.getElementById("next-button");

        const loading =
            document.getElementById("loading");

        const errorMessage =
            document.getElementById("error");


        async function loadPDF() {{

            try {{

                const loadingTask =
                    pdfjsLib.getDocument({{
                        data: pdfData
                    }});

                pdfDocument =
                    await loadingTask.promise;

                loading.style.display =
                    "none";

                canvas.style.display =
                    "block";

                await renderPage(
                    currentPage,
                    true
                );

            }} catch (error) {{

                console.error(error);

                loading.style.display =
                    "none";

                errorMessage.style.display =
                    "block";

                pageInfo.textContent =
                    "Error";

            }}

        }}


        async function calculateFitScale(page) {{

            const normalViewport =
                page.getViewport({{
                    scale: 1
                }});

            const availableWidth =
                Math.max(
                    container.clientWidth - 20,
                    100
                );

            const availableHeight =
                Math.max(
                    container.clientHeight - 20,
                    100
                );

            const widthScale =
                availableWidth /
                normalViewport.width;

            const heightScale =
                availableHeight /
                normalViewport.height;

            return Math.min(
                widthScale,
                heightScale
            );

        }}


        async function renderPage(
            pageNumber,
            recalculateFit = false
        ) {{

            if (
                !pdfDocument ||
                rendering
            ) {{
                return;
            }}

            rendering = true;

            try {{

                const page =
                    await pdfDocument.getPage(
                        pageNumber
                    );

                if (recalculateFit) {{

                    fitScale =
                        await calculateFitScale(
                            page
                        );

                }}

                const scale =
                    fitScale * zoomFactor;

                const viewport =
                    page.getViewport({{
                        scale: scale
                    }});

                const outputScale =
                    window.devicePixelRatio || 1;

                canvas.width =
                    Math.floor(
                        viewport.width *
                        outputScale
                    );

                canvas.height =
                    Math.floor(
                        viewport.height *
                        outputScale
                    );

                canvas.style.width =
                    Math.floor(
                        viewport.width
                    ) + "px";

                canvas.style.height =
                    Math.floor(
                        viewport.height
                    ) + "px";

                const transform =
                    outputScale !== 1
                        ? [
                            outputScale,
                            0,
                            0,
                            outputScale,
                            0,
                            0
                        ]
                        : null;

                await page.render({{
                    canvasContext: context,
                    viewport: viewport,
                    transform: transform
                }}).promise;

                currentPage =
                    pageNumber;

                pageInfo.textContent =
                    currentPage +
                    " / " +
                    pdfDocument.numPages;

                previousButton.disabled =
                    currentPage <= 1;

                nextButton.disabled =
                    currentPage >=
                    pdfDocument.numPages;

                container.scrollTop = 0;
                container.scrollLeft = 0;

            }} catch (error) {{

                console.error(error);

                errorMessage.style.display =
                    "block";

            }} finally {{

                rendering = false;

            }}

        }}


        function previousPage() {{

            if (
                !pdfDocument ||
                currentPage <= 1
            ) {{
                return;
            }}

            renderPage(
                currentPage - 1
            );

        }}


        function nextPage() {{

            if (
                !pdfDocument ||
                currentPage >= pdfDocument.numPages
            ) {{
                return;
            }}

            renderPage(
                currentPage + 1
            );

        }}


        function zoomIn() {{

            zoomFactor =
                Math.min(
                    zoomFactor + 0.2,
                    3
                );

            renderPage(
                currentPage
            );

        }}


        function zoomOut() {{

            zoomFactor =
                Math.max(
                    zoomFactor - 0.2,
                    0.4
                );

            renderPage(
                currentPage
            );

        }}


        function fitPage() {{

            zoomFactor = 1;

            renderPage(
                currentPage,
                true
            );

        }}


        document.addEventListener(
            "keydown",
            function(event) {{

                if (event.key === "ArrowLeft") {{
                    previousPage();
                }}

                if (
                    event.key === "ArrowRight" ||
                    event.key === " "
                ) {{

                    event.preventDefault();

                    nextPage();

                }}

            }}
        );


        let touchStartX = null;
        let touchStartY = null;


        container.addEventListener(
            "touchstart",
            function(event) {{

                if (event.touches.length !== 1) {{
                    return;
                }}

                touchStartX =
                    event.touches[0].clientX;

                touchStartY =
                    event.touches[0].clientY;

            }},
            {{
                passive: true
            }}
        );


        container.addEventListener(
            "touchend",
            function(event) {{

                if (
                    touchStartX === null ||
                    touchStartY === null
                ) {{
                    return;
                }}

                const touchEndX =
                    event.changedTouches[0].clientX;

                const touchEndY =
                    event.changedTouches[0].clientY;

                const differenceX =
                    touchEndX - touchStartX;

                const differenceY =
                    touchEndY - touchStartY;

                if (
                    Math.abs(differenceX) > 70 &&
                    Math.abs(differenceX) >
                        Math.abs(differenceY)
                ) {{

                    if (differenceX < 0) {{
                        nextPage();
                    }} else {{
                        previousPage();
                    }}

                }}

                touchStartX = null;
                touchStartY = null;

            }},
            {{
                passive: true
            }}
        );


        let resizeTimer = null;


        window.addEventListener(
            "resize",
            function() {{

                clearTimeout(
                    resizeTimer
                );

                resizeTimer = setTimeout(
                    function() {{

                        if (pdfDocument) {{

                            zoomFactor = 1;

                            renderPage(
                                currentPage,
                                true
                            );

                        }}

                    }},
                    250
                );

            }}
        );


        loadPDF();

    </script>

</body>

</html>
"""


# ----------------------------------------------------
# DISPLAY PDF.JS VIEWER
# ----------------------------------------------------

components.html(
    viewer_html,
    height=800,
    scrolling=False,
)
