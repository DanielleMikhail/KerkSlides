import base64
import html
from io import BytesIO

import gspread
import streamlit as st
import streamlit.components.v1 as components

from google.oauth2 import service_account
from googleapiclient.discovery import build
from pypdf import PdfReader, PdfWriter
from streamlit_sortables import sort_items


# ============================================================
# APP MODE
# ============================================================

# Normal application:
# https://your-app.streamlit.app
#
# Standalone presentation:
# https://your-app.streamlit.app/?view=presentation

presentation_mode = (
    st.query_params.get("view", "") == "presentation"
)


# ============================================================
# PAGE CONFIGURATION
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
# APPLICATION STYLING
# ============================================================

if presentation_mode:

    st.markdown(
        """
        <style>
            #MainMenu,
            header,
            footer,
            [data-testid="stToolbar"],
            [data-testid="stDecoration"],
            [data-testid="stStatusWidget"],
            [data-testid="stSidebar"],
            [data-testid="collapsedControl"] {
                display: none !important;
            }

            html,
            body,
            .stApp {
                background: #202124;
                overflow: hidden;
            }

            .block-container {
                max-width: 100%;
                padding: 0 !important;
                margin: 0 !important;
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

    st.markdown(
        """
        <style>
            .block-container {
                max-width: 1450px;
                padding-top: 1.5rem;
                padding-bottom: 3rem;
            }

            [data-testid="stHeader"] {
                background: rgba(255, 255, 255, 0);
            }

            div[data-testid="stVerticalBlockBorderWrapper"] {
                border-radius: 14px;
            }

            .presentation-link {
                display: block;
                width: 100%;
                padding: 0.75rem 1rem;
                border-radius: 8px;
                background: #ff4b4b;
                color: white !important;
                text-align: center;
                text-decoration: none !important;
                font-weight: 600;
                line-height: 1.25;
            }

            .presentation-link:hover {
                background: #e73b3b;
                color: white !important;
            }

            .document-count {
                padding: 10px 12px;
                margin-bottom: 12px;
                border-radius: 8px;
                background: #f5f5f5;
                color: #333333;
                font-size: 0.9rem;
            }

            .sync-box {
                padding: 12px;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                background: #fafafa;
            }

            .small-muted {
                color: #6b7280;
                font-size: 0.85rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
# VALIDATE CONFIGURATION
# ============================================================

if not SOURCE_FOLDER_ID:
    st.error(
        "SOURCE_FOLDER_ID is empty. Add the ID of your "
        "Google Drive source folder."
    )
    st.stop()

if not SPREADSHEET_ID:
    st.error(
        "SPREADSHEET_ID is empty. Add the ID of your "
        "Google Sheet."
    )
    st.stop()


# ============================================================
# GOOGLE CREDENTIALS
# ============================================================

try:

    credentials = (
        service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/spreadsheets",
            ],
        )
    )

except Exception as error:

    st.error(
        "Could not load the Google service-account credentials."
    )
    st.exception(error)
    st.stop()


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

try:

    sheet = gc.open_by_key(
        SPREADSHEET_ID
    ).sheet1

except Exception as error:

    st.error("Could not open the Google Sheet.")
    st.exception(error)
    st.stop()


# ============================================================
# GOOGLE SHEET SETUP
# ============================================================

def ensure_sheet_headers():
    """
    Ensure that the Google Sheet has the required columns.
    """

    required_headers = [
        "document_id",
        "document_name",
        "selected",
        "display_order",
    ]

    current_headers = sheet.row_values(1)

    if current_headers != required_headers:

        sheet.update(
            range_name="A1:D1",
            values=[required_headers],
        )


try:
    ensure_sheet_headers()

except Exception as error:

    st.error(
        "Could not prepare the Google Sheet. Make sure the "
        "service account has Editor access."
    )
    st.exception(error)
    st.stop()


# ============================================================
# GOOGLE DRIVE FUNCTIONS
# ============================================================

def get_google_docs():
    """
    Retrieve all Google Docs from the configured Drive folder.
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
            fields=(
                "nextPageToken, "
                "files(id, name, modifiedTime)"
            ),
            orderBy="name",
            pageToken=page_token,
            pageSize=1000,
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


def export_google_doc_as_pdf(document_id):
    """
    Export one Google Doc as PDF bytes.
    """

    request = drive_service.files().export_media(
        fileId=document_id,
        mimeType="application/pdf",
    )

    return request.execute()


# ============================================================
# GOOGLE SHEET FUNCTIONS
# ============================================================

def get_shared_order():
    """
    Read the selected document IDs from Google Sheets.

    The returned list is sorted using display_order.
    """

    records = sheet.get_all_records()

    selected_rows = []

    for row_index, row in enumerate(records, start=1):

        document_id = str(
            row.get("document_id", "")
        ).strip()

        selected_value = str(
            row.get("selected", "")
        ).strip().upper()

        if not document_id:
            continue

        if selected_value != "TRUE":
            continue

        try:
            display_order = int(
                row.get("display_order", row_index)
            )

        except (TypeError, ValueError):
            display_order = row_index

        selected_rows.append(
            {
                "document_id": document_id,
                "display_order": display_order,
            }
        )

    selected_rows.sort(
        key=lambda item: item["display_order"]
    )

    return [
        item["document_id"]
        for item in selected_rows
    ]


def save_shared_order(
    google_docs,
    ordered_document_ids,
):
    """
    Save the complete shared selection and ordering.

    All source documents remain in the Sheet. Selected documents
    receive TRUE and a display_order. Unselected documents receive
    FALSE and a blank display_order.
    """

    ordered_document_ids = [
        str(document_id)
        for document_id in ordered_document_ids
    ]

    order_by_id = {
        document_id: index
        for index, document_id in enumerate(
            ordered_document_ids,
            start=1,
        )
    }

    output_rows = [
        [
            "document_id",
            "document_name",
            "selected",
            "display_order",
        ]
    ]

    for file in google_docs:

        document_id = str(file["id"])
        document_name = file["name"]

        is_selected = (
            document_id in order_by_id
        )

        output_rows.append(
            [
                document_id,
                document_name,
                "TRUE" if is_selected else "FALSE",
                order_by_id.get(document_id, ""),
            ]
        )

    sheet.clear()

    sheet.update(
        range_name=(
            f"A1:D{len(output_rows)}"
        ),
        values=output_rows,
    )


# ============================================================
# DOCUMENT FUNCTIONS
# ============================================================

def get_files_in_order(
    google_docs,
    ordered_document_ids,
):
    """
    Match document IDs with Google Drive files while preserving
    the shared display order.
    """

    file_by_id = {
        str(file["id"]): file
        for file in google_docs
    }

    ordered_files = []

    for document_id in ordered_document_ids:

        file = file_by_id.get(
            str(document_id)
        )

        if file:
            ordered_files.append(file)

    return ordered_files


def compile_selected_pdf(selected_files):
    """
    Export the selected Google Docs and combine the exported PDFs
    in the chosen order.
    """

    if not selected_files:
        return None

    pdf_writer = PdfWriter()

    for file in selected_files:

        pdf_data = export_google_doc_as_pdf(
            file["id"]
        )

        pdf_reader = PdfReader(
            BytesIO(pdf_data)
        )

        for page in pdf_reader.pages:
            pdf_writer.add_page(page)

    combined_pdf = BytesIO()

    pdf_writer.write(combined_pdf)
    combined_pdf.seek(0)

    return combined_pdf.getvalue()


# ============================================================
# PDF.JS VIEWER
# ============================================================

def create_pdf_viewer(pdf_bytes):
    """
    Create a PDF.js viewer with:

    - one page at a time
    - previous and next navigation
    - keyboard navigation
    - swipe navigation
    - zoom controls
    - fit-to-screen
    - fullscreen where supported
    """

    pdf_base64 = base64.b64encode(
        pdf_bytes
    ).decode("utf-8")

    viewer_html = """
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

    <script
        src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js">
    </script>

    <style>

        * {
            box-sizing: border-box;
        }

        html,
        body {
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
        }

        #viewer {
            position: fixed;
            inset: 0;
            width: 100vw;
            height: 100vh;
            height: 100dvh;
            display: flex;
            flex-direction: column;
            background: #202124;
        }

        #toolbar {
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
        }

        button {
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
        }

        button:active {
            transform: scale(0.96);
            background: #e8eaed;
        }

        button:disabled {
            opacity: 0.4;
            cursor: default;
        }

        #page-info {
            min-width: 72px;
            color: white;
            text-align: center;
            font-size: 14px;
            white-space: nowrap;
        }

        #pdf-container {
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
        }

        #pdf-canvas {
            display: none;
            margin: 0 auto;
            background: white;
            box-shadow:
                0 3px 14px
                rgba(0, 0, 0, 0.45);
        }

        #loading {
            padding: 40px 20px;
            color: white;
            text-align: center;
            font-size: 16px;
        }

        #error {
            display: none;
            margin: 20px;
            padding: 15px;
            border-radius: 8px;
            background: #b3261e;
            color: white;
            text-align: center;
        }

        #viewer:fullscreen,
        #viewer:-webkit-full-screen {
            width: 100vw;
            height: 100vh;
        }

        @media (max-width: 600px) {

            #toolbar {
                min-height: 50px;
                gap: 4px;
            }

            button {
                min-width: 37px;
                min-height: 36px;
                padding: 7px 8px;
                font-size: 13px;
            }

            #page-info {
                min-width: 58px;
                font-size: 12px;
            }

            #pdf-container {
                padding-top: 5px;
            }
        }

    </style>

</head>

<body>

    <div id="viewer">

        <div id="toolbar">

            <button
                id="previous-button"
                onclick="previousPage()"
                aria-label="Previous page"
            >
                ◀
            </button>

            <span id="page-info">
                Loading...
            </span>

            <button
                id="next-button"
                onclick="nextPage()"
                aria-label="Next page"
            >
                ▶
            </button>

            <button
                onclick="zoomOut()"
                aria-label="Zoom out"
            >
                −
            </button>

            <button
                onclick="fitPage()"
                aria-label="Fit page"
            >
                Fit
            </button>

            <button
                onclick="zoomIn()"
                aria-label="Zoom in"
            >
                +
            </button>

            <button
                onclick="toggleFullscreen()"
                aria-label="Fullscreen"
            >
                ⛶
            </button>

        </div>

        <div id="pdf-container">

            <div id="loading">
                Loading presentation...
            </div>

            <div id="error">
                The presentation could not be loaded.
            </div>

            <canvas id="pdf-canvas"></canvas>

        </div>

    </div>

    <script>

        pdfjsLib.GlobalWorkerOptions.workerSrc =
            "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

        const pdfData = Uint8Array.from(
            window.atob("__PDF_BASE64__"),
            character => character.charCodeAt(0)
        );

        let pdfDocument = null;
        let currentPage = 1;
        let zoomFactor = 1.0;
        let fitScale = 1.0;
        let rendering = false;
        let pendingPage = null;

        const viewer =
            document.getElementById("viewer");

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

        const loadingMessage =
            document.getElementById("loading");

        const errorMessage =
            document.getElementById("error");


        async function loadPDF() {

            try {

                const loadingTask =
                    pdfjsLib.getDocument({
                        data: pdfData
                    });

                pdfDocument =
                    await loadingTask.promise;

                loadingMessage.style.display =
                    "none";

                canvas.style.display =
                    "block";

                await renderPage(
                    currentPage,
                    true
                );

            } catch (error) {

                console.error(error);

                loadingMessage.style.display =
                    "none";

                errorMessage.style.display =
                    "block";

                pageInfo.textContent =
                    "Error";
            }
        }


        async function calculateFitScale(page) {

            const unscaledViewport =
                page.getViewport({
                    scale: 1
                });

            const availableWidth =
                Math.max(
                    container.clientWidth - 16,
                    100
                );

            const availableHeight =
                Math.max(
                    container.clientHeight - 16,
                    100
                );

            const widthScale =
                availableWidth /
                unscaledViewport.width;

            const heightScale =
                availableHeight /
                unscaledViewport.height;

            return Math.min(
                widthScale,
                heightScale
            );
        }


        async function renderPage(
            pageNumber,
            recalculateFit = false
        ) {

            if (!pdfDocument) {
                return;
            }

            if (rendering) {
                pendingPage = pageNumber;
                return;
            }

            rendering = true;

            try {

                const page =
                    await pdfDocument.getPage(
                        pageNumber
                    );

                if (recalculateFit) {
                    fitScale =
                        await calculateFitScale(page);
                }

                const renderScale =
                    fitScale * zoomFactor;

                const viewport =
                    page.getViewport({
                        scale: renderScale
                    });

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

                await page.render({
                    canvasContext: context,
                    viewport: viewport,
                    transform: transform
                }).promise;

                currentPage = pageNumber;

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

            } catch (error) {

                console.error(error);
                errorMessage.style.display = "block";

            } finally {

                rendering = false;

                if (pendingPage !== null) {

                    const pageToRender =
                        pendingPage;

                    pendingPage = null;

                    renderPage(pageToRender);
                }
            }
        }


        function previousPage() {

            if (
                !pdfDocument ||
                currentPage <= 1
            ) {
                return;
            }

            renderPage(
                currentPage - 1
            );
        }


        function nextPage() {

            if (
                !pdfDocument ||
                currentPage >= pdfDocument.numPages
            ) {
                return;
            }

            renderPage(
                currentPage + 1
            );
        }


        function zoomIn() {

            zoomFactor =
                Math.min(
                    zoomFactor + 0.2,
                    3.0
                );

            renderPage(currentPage);
        }


        function zoomOut() {

            zoomFactor =
                Math.max(
                    zoomFactor - 0.2,
                    0.4
                );

            renderPage(currentPage);
        }


        function fitPage() {

            zoomFactor = 1.0;

            renderPage(
                currentPage,
                true
            );
        }


        async function toggleFullscreen() {

            try {

                if (
                    document.fullscreenElement ||
                    document.webkitFullscreenElement
                ) {

                    if (document.exitFullscreen) {
                        await document.exitFullscreen();

                    } else if (
                        document.webkitExitFullscreen
                    ) {
                        document.webkitExitFullscreen();
                    }

                    return;
                }

                if (viewer.requestFullscreen) {
                    await viewer.requestFullscreen();

                } else if (
                    viewer.webkitRequestFullscreen
                ) {
                    viewer.webkitRequestFullscreen();
                }

            } catch (error) {

                console.log(
                    "Fullscreen is not available:",
                    error
                );
            }
        }


        document.addEventListener(
            "keydown",
            function(event) {

                if (
                    event.key === "ArrowLeft" ||
                    event.key === "PageUp"
                ) {
                    previousPage();
                }

                if (
                    event.key === "ArrowRight" ||
                    event.key === "PageDown" ||
                    event.key === " "
                ) {
                    event.preventDefault();
                    nextPage();
                }
            }
        );


        let touchStartX = null;
        let touchStartY = null;


        container.addEventListener(
            "touchstart",
            function(event) {

                if (event.touches.length !== 1) {
                    return;
                }

                touchStartX =
                    event.touches[0].clientX;

                touchStartY =
                    event.touches[0].clientY;
            },
            {
                passive: true
            }
        );


        container.addEventListener(
            "touchend",
            function(event) {

                if (
                    touchStartX === null ||
                    touchStartY === null ||
                    event.changedTouches.length !== 1
                ) {
                    return;
                }

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
                ) {

                    if (differenceX < 0) {
                        nextPage();
                    } else {
                        previousPage();
                    }
                }

                touchStartX = null;
                touchStartY = null;
            },
            {
                passive: true
            }
        );


        function refitCurrentPage() {

            setTimeout(
                function() {

                    if (pdfDocument) {

                        zoomFactor = 1.0;

                        renderPage(
                            currentPage,
                            true
                        );
                    }
                },
                250
            );
        }


        let resizeTimer = null;


        window.addEventListener(
            "resize",
            function() {

                clearTimeout(resizeTimer);

                resizeTimer = setTimeout(
                    refitCurrentPage,
                    250
                );
            }
        );


        document.addEventListener(
            "fullscreenchange",
            refitCurrentPage
        );


        document.addEventListener(
            "webkitfullscreenchange",
            refitCurrentPage
        );


        loadPDF();

    </script>

</body>
</html>
"""

    return viewer_html.replace(
        "__PDF_BASE64__",
        pdf_base64,
    )


# ============================================================
# LOAD GOOGLE DRIVE DOCUMENTS
# ============================================================

try:

    google_docs = get_google_docs()

except Exception as error:

    st.error(
        "Could not load the Google Docs from Google Drive."
    )
    st.exception(error)
    st.stop()


file_by_id = {
    str(file["id"]): file
    for file in google_docs
}


# ============================================================
# PRESENTATION MODE
# ============================================================

if presentation_mode:

    try:

        shared_order = get_shared_order()

        selected_files = get_files_in_order(
            google_docs,
            shared_order,
        )

    except Exception as error:

        st.error(
            "Could not load the shared presentation."
        )
        st.exception(error)
        st.stop()


    if not selected_files:

        st.markdown(
            """
            <div style="
                color: white;
                padding: 60px 20px;
                text-align: center;
                font-family: Arial, sans-serif;
            ">
                <h2>No documents selected</h2>
                <p>
                    Return to KerkSlides and add documents
                    to the shared presentation first.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.stop()


    try:

        with st.spinner(
            "Creating presentation..."
        ):

            pdf_bytes = compile_selected_pdf(
                selected_files
            )

    except Exception as error:

        st.error(
            "Could not compile the presentation."
        )
        st.exception(error)
        st.stop()


    viewer_html = create_pdf_viewer(
        pdf_bytes
    )

    components.html(
        viewer_html,
        height=1400,
        scrolling=False,
    )

    st.stop()


# ============================================================
# INITIALIZE NORMAL APP STATE
# ============================================================

try:

    shared_order = get_shared_order()

except Exception as error:

    st.error(
        "Could not read the selection from Google Sheets."
    )
    st.exception(error)
    st.stop()


valid_shared_order = [
    document_id
    for document_id in shared_order
    if document_id in file_by_id
]


if "draft_order" not in st.session_state:

    st.session_state.draft_order = (
        valid_shared_order.copy()
    )


# ============================================================
# PAGE HEADER
# ============================================================

header_left, header_right = st.columns(
    [5, 1]
)

with header_left:

    st.title("⛪ KerkSlides")

    st.caption(
        "Create, order, preview, and share one synchronized "
        "presentation."
    )

with header_right:

    st.write("")

    if st.button(
        "🔄 Refresh",
        use_container_width=True,
        help=(
            "Reload the most recent shared selection "
            "from Google Sheets."
        ),
    ):

        try:

            refreshed_order = get_shared_order()

            st.session_state.draft_order = [
                document_id
                for document_id in refreshed_order
                if document_id in file_by_id
            ]

            st.rerun()

        except Exception as error:

            st.error("Could not refresh the presentation.")
            st.exception(error)


st.divider()


# ============================================================
# MAIN LAYOUT
# ============================================================

workspace_column, presentation_column = st.columns(
    [2.1, 1],
    gap="large",
)


# ============================================================
# LEFT SIDE: DOCUMENT WORKSPACE
# ============================================================

with workspace_column:

    with st.container(border=True):

        st.subheader("Build presentation")

        st.caption(
            "Choose a document from the dropdown, add it, "
            "and drag the selected documents into the correct order."
        )


        # ----------------------------------------------------
        # ADD DOCUMENT DROPDOWN
        # ----------------------------------------------------

        available_files = [
            file
            for file in google_docs
            if str(file["id"])
            not in st.session_state.draft_order
        ]

        if available_files:

            available_file_by_name = {
                file["name"]: str(file["id"])
                for file in available_files
            }

            dropdown_column, add_column = st.columns(
                [4, 1]
            )

            with dropdown_column:

                selected_document_name = st.selectbox(
                    "Document",
                    options=list(
                        available_file_by_name.keys()
                    ),
                    label_visibility="collapsed",
                    placeholder="Choose a document",
                )

            with add_column:

                add_clicked = st.button(
                    "➕ Add",
                    use_container_width=True,
                )

            if (
                add_clicked
                and selected_document_name
            ):

                selected_document_id = (
                    available_file_by_name[
                        selected_document_name
                    ]
                )

                if (
                    selected_document_id
                    not in st.session_state.draft_order
                ):

                    st.session_state.draft_order.append(
                        selected_document_id
                    )

                    st.rerun()

        else:

            st.info(
                "All available Google Docs have already "
                "been added."
            )


        st.divider()


        # ----------------------------------------------------
        # ORDER DOCUMENTS
        # ----------------------------------------------------

        st.markdown("#### Presentation order")

        if not st.session_state.draft_order:

            st.info(
                "No documents have been added yet. "
                "Use the dropdown above to add a document."
            )

        else:

            st.caption(
                "Drag the cards up or down to change "
                "the presentation order."
            )

            sortable_labels = []

            label_to_id = {}

            for position, document_id in enumerate(
                st.session_state.draft_order,
                start=1,
            ):

                file = file_by_id.get(document_id)

                if not file:
                    continue

                label = (
                    f"{position}. {file['name']}"
                )

                sortable_labels.append(label)
                label_to_id[label] = document_id


            reordered_labels = sort_items(
                sortable_labels,
                direction="vertical",
                key="presentation_order_sorter",
            )


            reordered_ids = [
                label_to_id[label]
                for label in reordered_labels
                if label in label_to_id
            ]


            if (
                reordered_ids
                and reordered_ids
                != st.session_state.draft_order
            ):

                st.session_state.draft_order = (
                    reordered_ids
                )


            st.markdown("##### Remove documents")

            remove_file_by_name = {
                file_by_id[document_id]["name"]: document_id
                for document_id
                in st.session_state.draft_order
                if document_id in file_by_id
            }

            remove_column, remove_button_column = st.columns(
                [4, 1]
            )

            with remove_column:

                document_to_remove_name = st.selectbox(
                    "Remove document",
                    options=list(
                        remove_file_by_name.keys()
                    ),
                    label_visibility="collapsed",
                    key="remove_document_dropdown",
                )

            with remove_button_column:

                remove_clicked = st.button(
                    "🗑️ Remove",
                    use_container_width=True,
                )

            if (
                remove_clicked
                and document_to_remove_name
            ):

                document_to_remove_id = (
                    remove_file_by_name[
                        document_to_remove_name
                    ]
                )

                st.session_state.draft_order = [
                    document_id
                    for document_id
                    in st.session_state.draft_order
                    if document_id
                    != document_to_remove_id
                ]

                st.rerun()


        # ----------------------------------------------------
        # SAVE SHARED PRESENTATION
        # ----------------------------------------------------

        st.divider()

        save_column, reset_column = st.columns(
            [2, 1]
        )

        with save_column:

            save_clicked = st.button(
                "💾 Save shared presentation",
                type="primary",
                use_container_width=True,
            )

        with reset_column:

            reset_clicked = st.button(
                "↩ Reset",
                use_container_width=True,
                help=(
                    "Discard local changes and restore the "
                    "currently saved shared presentation."
                ),
            )


        if save_clicked:

            try:

                with st.spinner(
                    "Saving shared presentation..."
                ):

                    save_shared_order(
                        google_docs,
                        st.session_state.draft_order,
                    )

                st.success(
                    "Shared presentation saved. Everyone will "
                    "now see the same documents and order. ✅"
                )

            except Exception as error:

                st.error(
                    "Could not save the shared presentation."
                )
                st.exception(error)


        if reset_clicked:

            try:

                current_shared_order = get_shared_order()

                st.session_state.draft_order = [
                    document_id
                    for document_id
                    in current_shared_order
                    if document_id in file_by_id
                ]

                st.rerun()

            except Exception as error:

                st.error(
                    "Could not restore the shared presentation."
                )
                st.exception(error)


   
# ============================================================
# RIGHT SIDE: SHARED PRESENTATION PANEL
# ============================================================

with presentation_column:

    with st.container(border=True):

        st.subheader("Shared presentation")

        st.markdown(
            """
            <div class="sync-box">
                <strong>☁️ Shared and synchronized</strong>
                <div class="small-muted">
                    The saved document selection and order are
                    stored in Google Sheets.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.write("")

        draft_files = get_files_in_order(
            google_docs,
            st.session_state.draft_order,
        )

        st.markdown(
            f"""
            <div class="document-count">
                <strong>{len(draft_files)}</strong>
                document{"s" if len(draft_files) != 1 else ""}
                currently in the workspace
            </div>
            """,
            unsafe_allow_html=True,
        )


        # ----------------------------------------------------
        # SELECTED DOCUMENT LIST
        # ----------------------------------------------------

        with st.expander(
            "📑 View document order",
            expanded=True,
        ):

            if not draft_files:

                st.caption(
                    "No documents selected."
                )

            else:

                for index, file in enumerate(
                    draft_files,
                    start=1,
                ):

                    st.write(
                        f"**{index}.** {file['name']}"
                    )


        # ----------------------------------------------------
        # BUILD COMBINED PDF
        # ----------------------------------------------------

        combined_pdf_bytes = None

        if draft_files:

            try:

                with st.spinner(
                    "Creating combined preview..."
                ):

                    combined_pdf_bytes = (
                        compile_selected_pdf(
                            draft_files
                        )
                    )

            except Exception as error:

                st.error(
                    "Could not create the combined PDF."
                )

                with st.expander(
                    "View technical error"
                ):
                    st.exception(error)


        # ----------------------------------------------------
        # PDF INFORMATION AND DOWNLOAD
        # ----------------------------------------------------

        if combined_pdf_bytes:

            try:

                combined_reader = PdfReader(
                    BytesIO(combined_pdf_bytes)
                )

                page_count = len(
                    combined_reader.pages
                )

                st.metric(
                    "Combined PDF pages",
                    page_count,
                )

            except Exception:

                page_count = None


            st.download_button(
                "⬇️ Download combined PDF",
                data=combined_pdf_bytes,
                file_name=OUTPUT_FILE_NAME,
                mime="application/pdf",
                use_container_width=True,
            )


        # ----------------------------------------------------
        # OPEN IN NEW BROWSER TAB
        # ----------------------------------------------------

        if draft_files:

            st.markdown(
                """
                ?view=presentation
                    🎥 Open standalone presentation
                </a>
                """,
                unsafe_allow_html=True,
            )

        else:

            st.button(
                "🎥 Open standalone presentation",
                disabled=True,
                use_container_width=True,
            )


        st.caption(
            "The standalone presentation opens in a new browser "
            "tab. It uses the last version saved to Google Sheets."
        )

        st.info(
            "Save the shared presentation before opening it if "
            "you changed the documents or their order."
        )


    # --------------------------------------------------------
    # COMBINED PREVIEW
    # --------------------------------------------------------

    if combined_pdf_bytes:

        with st.container(border=True):

            st.subheader("Combined preview")

            st.caption(
                "Preview of the current workspace order."
            )

            combined_viewer_html = (
                create_pdf_viewer(
                    combined_pdf_bytes
                )
            )

            components.html(
                combined_viewer_html,
                height=600,
                scrolling=False,
            )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "KerkSlides • Shared through Google Sheets • "
    "Documents loaded from Google Drive"
)
