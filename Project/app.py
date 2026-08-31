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

# Normal URL:
# https://your-app.streamlit.app
#
# Standalone presentation URL:
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
    initial_sidebar_state=(
        "collapsed"
        if presentation_mode
        else "expanded"
    ),
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
# PRESENTATION MODE STYLING
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
# GOOGLE DRIVE FUNCTIONS
# ============================================================

def get_google_docs():
    """
    Retrieve all Google Docs from the configured folder.
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


# ============================================================
# GOOGLE SHEET FUNCTIONS
# ============================================================

def get_ordered_selection():
    """
    Read selected document IDs from Google Sheets in their
    saved presentation order.
    """

    rows = sheet.get_all_records()

    selected_rows = [
        row
        for row in rows
        if (
            row.get("document_id")
            and str(row.get("selected", ""))
            .strip()
            .upper()
            == "TRUE"
        )
    ]

    def get_order_value(row):

        order_value = str(
            row.get("order", "")
        ).strip()

        if order_value.isdigit():
            return int(order_value)

        return 999999

    selected_rows.sort(
        key=get_order_value
    )

    return [
        str(row["document_id"])
        for row in selected_rows
    ]


def save_ordered_selection(
    google_docs,
    ordered_document_ids,
):
    """
    Save the selected documents and their order to Google
    Sheets.

    Expected columns:
    A: document_id
    B: document_name
    C: selected
    D: order
    """

    rows = sheet.get_all_records()

    row_by_id = {
        str(row["document_id"]): index + 2
        for index, row in enumerate(rows)
        if row.get("document_id")
    }

    ordered_document_ids = [
        str(document_id)
        for document_id in ordered_document_ids
    ]

    order_by_id = {
        document_id: position
        for position, document_id in enumerate(
            ordered_document_ids,
            start=1,
        )
    }

    new_rows = []

    for document in google_docs:

        document_id = str(
            document["id"]
        )

        document_name = document["name"]

        if document_id in order_by_id:

            selected_value = "TRUE"

            order_value = order_by_id[
                document_id
            ]

        else:

            selected_value = "FALSE"
            order_value = ""

        row_number = row_by_id.get(
            document_id
        )

        if row_number:

            sheet.update(
                range_name=(
                    f"A{row_number}:D{row_number}"
                ),
                values=[
                    [
                        document_id,
                        document_name,
                        selected_value,
                        order_value,
                    ]
                ],
            )

        else:

            new_rows.append(
                [
                    document_id,
                    document_name,
                    selected_value,
                    order_value,
                ]
            )

    if new_rows:

        sheet.append_rows(
            new_rows,
            value_input_option="USER_ENTERED",
        )


# ============================================================
# DOCUMENT FUNCTIONS
# ============================================================

def get_ordered_files(
    google_docs,
    ordered_document_ids,
):
    """
    Return selected Google Docs in the saved presentation
    order.
    """

    file_by_id = {
        str(document["id"]): document
        for document in google_docs
    }

    return [
        file_by_id[document_id]
        for document_id in ordered_document_ids
        if document_id in file_by_id
    ]


def compile_selected_pdf(
    selected_files,
):
    """
    Export the selected Google Docs as PDFs and combine them
    in the selected order.
    """

    pdf_writer = PdfWriter()

    for document in selected_files:

        request = drive_service.files().export_media(
            fileId=document["id"],
            mimeType="application/pdf",
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


# ============================================================
# PRESENTATION VIEWER
# ============================================================

def create_pdf_viewer(
    pdf_bytes,
):
    """
    Create a PDF.js presentation viewer.

    Only one PDF page is rendered at a time.
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
                min-width: 58px;
                font-size: 12px;
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
            window.atob("{pdf_base64}"),
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


        async function loadPDF() {{

            try {{

                const loadingTask =
                    pdfjsLib.getDocument({{
                        data: pdfData
                    }});

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

            }} catch (error) {{

                console.error(error);

                loadingMessage.style.display =
                    "none";

                errorMessage.style.display =
                    "block";

                pageInfo.textContent =
                    "Error";

            }}

        }}


        async function calculateFitScale(
            page
        ) {{

            const unscaledViewport =
                page.getViewport({{
                    scale: 1
                }});

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

        }}


        async function renderPage(
            pageNumber,
            recalculateFit = false
        ) {{

            if (!pdfDocument) {{
                return;
            }}

            if (rendering) {{

                pendingPage =
                    pageNumber;

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

                const renderScale =
                    fitScale * zoomFactor;

                const viewport =
                    page.getViewport({{
                        scale: renderScale
                    }});

                const outputScale =
                    window.devicePixelRatio || 1;

                canvas.width =
                    Math.floor(
                        viewport.width * outputScale
                    );

                canvas.height =
                    Math.floor(
                        viewport.height * outputScale
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

                if (pendingPage !== null) {{

                    const pageToRender =
                        pendingPage;

                    pendingPage = null;

                    renderPage(
                        pageToRender
                    );

                }}

            }}

        }}


        function previousPage() {{

            if (
                pdfDocument &&
                currentPage > 1
            ) {{

                renderPage(
                    currentPage - 1
                );

            }}

        }}


        function nextPage() {{

            if (
                pdfDocument &&
                currentPage < pdfDocument.numPages
            ) {{

                renderPage(
                    currentPage + 1
                );

            }}

        }}


        function zoomIn() {{

            zoomFactor =
                Math.min(
                    zoomFactor + 0.2,
                    3.0
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

            zoomFactor = 1.0;

            renderPage(
                currentPage,
                true
            );

        }}


        async function toggleFullscreen() {{

            try {{

                if (
                    document.fullscreenElement ||
                    document.webkitFullscreenElement
                ) {{

                    if (document.exitFullscreen) {{

                        await document.exitFullscreen();

                    }} else if (
                        document.webkitExitFullscreen
                    ) {{

                        document.webkitExitFullscreen();

                    }}

                    return;

                }}

                if (viewer.requestFullscreen) {{

                    await viewer.requestFullscreen();

                }} else if (
                    viewer.webkitRequestFullscreen
                ) {{

                    viewer.webkitRequestFullscreen();

                }}

            }} catch (error) {{

                console.log(
                    "Fullscreen is not available.",
                    error
                );

            }}

        }}


        document.addEventListener(
            "keydown",
            function(event) {{

                if (
                    event.key === "ArrowLeft" ||
                    event.key === "PageUp"
                ) {{

                    previousPage();

                }}

                if (
                    event.key === "ArrowRight" ||
                    event.key === "PageDown" ||
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
                    touchStartY === null ||
                    event.changedTouches.length !== 1
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

                            zoomFactor = 1.0;

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

    return viewer_html


# ============================================================
# LOAD GOOGLE DOCS
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
# PRESENTATION MODE
# ============================================================

if presentation_mode:

    try:

        ordered_document_ids = (
            get_ordered_selection()
        )

        selected_files = get_ordered_files(
            google_docs,
            ordered_document_ids,
        )

    except Exception as error:

        st.error(
            "Could not load the selected documents."
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
                    to the presentation first.
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
        height=1200,
        scrolling=False,
    )

    st.stop()


# ============================================================
# NORMAL APP TITLE
# ============================================================

st.title(
    "⛪ KerkSlides"
)


# ============================================================
# INITIALIZE SELECTION
# ============================================================

if "ordered_document_ids" not in st.session_state:

    try:

        st.session_state.ordered_document_ids = (
            get_ordered_selection()
        )

    except Exception as error:

        st.error(
            "Could not load the selected documents."
        )

        st.exception(error)

        st.stop()


# ============================================================
# REMOVE DOCUMENTS THAT NO LONGER EXIST
# ============================================================

available_document_ids = {
    str(document["id"])
    for document in google_docs
}

st.session_state.ordered_document_ids = [
    document_id
    for document_id
    in st.session_state.ordered_document_ids
    if document_id in available_document_ids
]


# ============================================================
# DOCUMENT LOOKUPS
# ============================================================

document_name_by_id = {
    str(document["id"]): document["name"]
    for document in google_docs
}


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title(
        "⛪ KerkSlides"
    )

    st.caption(
        "Create and manage the presentation."
    )


    # ========================================================
    # SELECT DOCUMENTS
    # ========================================================

    with st.expander(
        "📁 Select documents",
        expanded=True,
    ):

        selected_ids = set(
            st.session_state.ordered_document_ids
        )

        available_documents = [
            document
            for document in google_docs
            if str(document["id"])
            not in selected_ids
        ]

        available_ids = [
            str(document["id"])
            for document in available_documents
        ]


        # ----------------------------------------------------
        # DOCUMENT DROPDOWN
        # ----------------------------------------------------

        selected_document_id = st.selectbox(
            "Choose a document",
            options=available_ids,
            index=None,
            placeholder=(
                "Select a document..."
                if available_ids
                else "All documents have been added"
            ),
            format_func=lambda document_id: (
                document_name_by_id.get(
                    document_id,
                    document_id,
                )
            ),
            key="document_dropdown",
            disabled=not available_ids,
        )


        # ----------------------------------------------------
        # ADD DOCUMENT
        # ----------------------------------------------------

        if st.button(
            "➕ Add document",
            type="primary",
            use_container_width=True,
            disabled=(
                selected_document_id is None
            ),
        ):

            if (
                selected_document_id
                not in
                st.session_state.ordered_document_ids
            ):

                st.session_state.ordered_document_ids.append(
                    selected_document_id
                )

            try:

                save_ordered_selection(
                    google_docs,
                    st.session_state.ordered_document_ids,
                )

                if "document_dropdown" in st.session_state:
                    del st.session_state[
                        "document_dropdown"
                    ]

                st.rerun()

            except Exception as error:

                st.error(
                    "Could not add the document."
                )

                st.exception(error)


        st.divider()


        # ----------------------------------------------------
        # SELECTED DOCUMENT LIST
        # ----------------------------------------------------

        st.subheader(
            "Added documents"
        )

        number_of_documents = len(
            st.session_state.ordered_document_ids
        )

        if number_of_documents == 0:

            st.info(
                "No documents have been added yet."
            )

        else:

            st.caption(
                f"{number_of_documents} documents selected"
            )

            for index, document_id in enumerate(
                st.session_state.ordered_document_ids
            ):

                document_name = (
                    document_name_by_id.get(
                        document_id,
                        "Unknown document",
                    )
                )

                with st.container(
                    border=True
                ):

                    st.markdown(
                        f"**{index + 1}. {document_name}**"
                    )

                    up_column, down_column, remove_column = (
                        st.columns(
                            [1, 1, 1]
                        )
                    )


                    # ----------------------------------------
                    # MOVE UP
                    # ----------------------------------------

                    with up_column:

                        if st.button(
                            "↑",
                            key=f"up_{document_id}",
                            help="Move up",
                            use_container_width=True,
                            disabled=(index == 0),
                        ):

                            ordered_ids = (
                                st.session_state
                                .ordered_document_ids
                            )

                            ordered_ids[
                                index - 1
                            ], ordered_ids[index] = (
                                ordered_ids[index],
                                ordered_ids[index - 1],
                            )

                            try:

                                save_ordered_selection(
                                    google_docs,
                                    ordered_ids,
                                )

                                st.rerun()

                            except Exception as error:

                                st.error(
                                    "Could not change the order."
                                )

                                st.exception(error)


                    # ----------------------------------------
                    # MOVE DOWN
                    # ----------------------------------------

                    with down_column:

                        if st.button(
                            "↓",
                            key=f"down_{document_id}",
                            help="Move down",
                            use_container_width=True,
                            disabled=(
                                index
                                == number_of_documents - 1
                            ),
                        ):

                            ordered_ids = (
                                st.session_state
                                .ordered_document_ids
                            )

                            ordered_ids[
                                index + 1
                            ], ordered_ids[index] = (
                                ordered_ids[index],
                                ordered_ids[index + 1],
                            )

                            try:

                                save_ordered_selection(
                                    google_docs,
                                    ordered_ids,
                                )

                                st.rerun()

                            except Exception as error:

                                st.error(
                                    "Could not change the order."
                                )

                                st.exception(error)


                    # ----------------------------------------
                    # REMOVE
                    # ----------------------------------------

                    with remove_column:

                        if st.button(
                            "✕",
                            key=f"remove_{document_id}",
                            help="Remove document",
                            use_container_width=True,
                        ):

                            st.session_state.ordered_document_ids.remove(
                                document_id
                            )

                            try:

                                save_ordered_selection(
                                    google_docs,
                                    st.session_state
                                    .ordered_document_ids,
                                )

                                st.rerun()

                            except Exception as error:

                                st.error(
                                    "Could not remove the document."
                                )

                                st.exception(error)


    # ========================================================
    # REVIEW
    # ========================================================

    with st.expander(
        "👀 Review",
        expanded=False,
    ):

        ordered_document_ids = (
            st.session_state.ordered_document_ids
        )

        selected_files = get_ordered_files(
            google_docs,
            ordered_document_ids,
        )

        if not selected_files:

            st.info(
                "Add at least one document first."
            )

        else:

            st.write(
                f"**{len(selected_files)} documents** "
                "will be combined."
            )

            st.caption(
                "The documents will be combined in the "
                "order shown above."
            )

            try:

                with st.spinner(
                    "Creating combined PDF..."
                ):

                    pdf_bytes = compile_selected_pdf(
                        selected_files
                    )

            except Exception as error:

                st.error(
                    "Could not create the combined PDF."
                )

                st.exception(error)

                st.stop()


            # ------------------------------------------------
            # DOWNLOAD
            # ------------------------------------------------

            st.download_button(
                "⬇️ Download combined PDF",
                data=pdf_bytes,
                file_name=OUTPUT_FILE_NAME,
                mime="application/pdf",
                use_container_width=True,
            )


            # ------------------------------------------------
            # STANDALONE PRESENTATION
            # ------------------------------------------------

            st.link_button(
                "🎥 Open standalone presentation",
                "?view=presentation",
                type="primary",
                use_container_width=True,
            )


# ============================================================
# MAIN SCREEN
# ============================================================

st.subheader(
    "Create your presentation"
)

number_selected = len(
    st.session_state.ordered_document_ids
)

if number_selected == 0:

    st.info(
        "Open the sidebar and add documents to begin."
    )

else:

    st.success(
        f"{number_selected} documents currently selected."
    )

    st.write(
        "Use the sidebar to add documents, remove documents, "
        "or change their order."
    )

    st.write(
        "When the presentation is ready, open **Review** in "
        "the sidebar to download the PDF or start the "
        "standalone presentation."
    )
