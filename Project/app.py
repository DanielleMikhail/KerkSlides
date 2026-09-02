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
# CONFIGURATION
# ============================================================

SOURCE_FOLDER_ID = "1q-5HeICSq5zBoQAEDb_PNA3iMXbgrNBn"
SPREADSHEET_ID = "1f4EFf5HeWCUtPtqYtsoooOAXpibKiuXEoWU0CHAOjWQ"

OUTPUT_FILE_NAME = "KerkSlides_Compiled.pdf"

REQUIRED_HEADERS = [
    "document_id",
    "document_name",
    "selected",
    "display_order",
]


# ============================================================
# APPLICATION MODE
# ============================================================

presentation_mode = (
    st.query_params.get("view", "")
    == "presentation"
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
# STYLING
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
                max-width: 100% !important;
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
                background: transparent;
            }

            div[data-testid="stVerticalBlockBorderWrapper"] {
                border-radius: 14px;
            }

            .presentation-link {
                display: flex;
                width: 100%;
                min-height: 42px;
                padding: 0.65rem 1rem;
                border-radius: 8px;
                background: #ff4b4b;
                color: white !important;
                align-items: center;
                justify-content: center;
                text-align: center;
                text-decoration: none !important;
                font-weight: 600;
                line-height: 1.25;
            }

            .presentation-link:hover {
                background: #e73b3b;
                color: white !important;
                text-decoration: none !important;
            }

            .presentation-order-box {
                padding: 12px 14px;
                margin-bottom: 14px;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                background: #fafafa;
            }

            .presentation-order-item {
                padding: 7px 0;
                border-bottom: 1px solid #eeeeee;
                color: #333333;
                font-size: 0.95rem;
            }

            .presentation-order-item:last-child {
                border-bottom: none;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# VALIDATE CONFIGURATION
# ============================================================

if not SOURCE_FOLDER_ID or SOURCE_FOLDER_ID == "XX":
    st.error("SOURCE_FOLDER_ID is not configured.")
    st.stop()

if not SPREADSHEET_ID or SPREADSHEET_ID == "XX":
    st.error("SPREADSHEET_ID is not configured.")
    st.stop()


# ============================================================
# GOOGLE CONNECTION
# ============================================================

try:

    credentials = (
        service_account
        .Credentials
        .from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/spreadsheets",
            ],
        )
    )

    drive_service = build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    sheet = (
        gspread
        .authorize(credentials)
        .open_by_key(SPREADSHEET_ID)
        .sheet1
    )

except Exception as error:

    st.error(
        "Could not connect to Google Drive "
        "or Google Sheets."
    )

    st.exception(error)
    st.stop()


# ============================================================
# GOOGLE SHEET SETUP
# ============================================================

def ensure_sheet_headers():

    current_headers = sheet.row_values(1)

    if current_headers != REQUIRED_HEADERS:

        sheet.update(
            range_name="A1:D1",
            values=[REQUIRED_HEADERS],
            value_input_option="RAW",
        )


try:
    ensure_sheet_headers()

except Exception as error:

    st.error(
        "Could not prepare the Google Sheet. "
        "Make sure the service account has Editor access."
    )

    st.exception(error)
    st.stop()


# ============================================================
# GOOGLE DRIVE FUNCTIONS
# ============================================================

@st.cache_data(
    show_spinner=False,
    ttl=60,
)
def get_google_docs():

    files = []
    page_token = None

    while True:

        result = (
            drive_service
            .files()
            .list(
                q=(
                    f"'{SOURCE_FOLDER_ID}' in parents "
                    "and mimeType="
                    "'application/vnd.google-apps.document' "
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
            )
            .execute()
        )

        files.extend(
            result.get("files", [])
        )

        page_token = result.get(
            "nextPageToken"
        )

        if not page_token:
            return files


def export_google_doc_as_pdf(
    document_id,
):

    request = (
        drive_service
        .files()
        .export_media(
            fileId=document_id,
            mimeType="application/pdf",
        )
    )

    return request.execute()


# ============================================================
# GOOGLE SHEET FUNCTIONS
# ============================================================

def convert_to_display_order(
    value,
    fallback,
):

    try:
        return int(
            float(
                str(value).strip()
            )
        )

    except (TypeError, ValueError):
        return fallback


def get_shared_order():

    selected_rows = []

    records = sheet.get_all_records()

    for fallback_order, row in enumerate(
        records,
        start=1,
    ):

        document_id = str(
            row.get(
                "document_id",
                "",
            )
        ).strip()

        selected_value = str(
            row.get(
                "selected",
                "",
            )
        ).strip().upper()

        if not document_id:
            continue

        if selected_value not in {
            "TRUE",
            "1",
            "YES",
        }:
            continue

        display_order = (
            convert_to_display_order(
                row.get(
                    "display_order",
                    "",
                ),
                fallback_order,
            )
        )

        selected_rows.append(
            {
                "document_id": document_id,
                "display_order": display_order,
                "fallback_order": fallback_order,
            }
        )

    selected_rows.sort(
        key=lambda item: (
            item["display_order"],
            item["fallback_order"],
        )
    )

    return [
        item["document_id"]
        for item in selected_rows
    ]


def save_shared_order(
    google_docs,
    ordered_document_ids,
):

    ordered_document_ids = [
        str(document_id).strip()
        for document_id
        in ordered_document_ids
        if str(document_id).strip()
    ]

    ordered_document_ids = list(
        dict.fromkeys(
            ordered_document_ids
        )
    )

    valid_document_ids = {
        str(file["id"])
        for file in google_docs
    }

    ordered_document_ids = [
        document_id
        for document_id
        in ordered_document_ids
        if document_id
        in valid_document_ids
    ]

    order_by_id = {
        document_id: position
        for position, document_id
        in enumerate(
            ordered_document_ids,
            start=1,
        )
    }

    output_rows = [
        REQUIRED_HEADERS
    ]

    for file in google_docs:

        document_id = str(
            file["id"]
        )

        document_name = str(
            file["name"]
        )

        is_selected = (
            document_id in order_by_id
        )

        output_rows.append(
            [
                document_id,
                document_name,
                (
                    "TRUE"
                    if is_selected
                    else "FALSE"
                ),
                order_by_id.get(
                    document_id,
                    "",
                ),
            ]
        )

    required_rows = max(
        len(output_rows),
        2,
    )

    if sheet.row_count < required_rows:

        sheet.add_rows(
            required_rows
            - sheet.row_count
        )

    sheet.batch_clear(
        [
            f"A1:D{sheet.row_count}",
        ]
    )

    sheet.update(
        range_name=(
            f"A1:D{len(output_rows)}"
        ),
        values=output_rows,
        value_input_option="RAW",
    )

    saved_order = get_shared_order()

    if saved_order != ordered_document_ids:

        raise RuntimeError(
            "The saved presentation order "
            "could not be verified."
        )

    return saved_order


# ============================================================
# DOCUMENT FUNCTIONS
# ============================================================

def clean_document_order(
    document_ids,
    file_by_id,
):

    output = []
    seen_ids = set()

    for document_id in document_ids:

        document_id = str(
            document_id
        )

        if document_id not in file_by_id:
            continue

        if document_id in seen_ids:
            continue

        output.append(
            document_id
        )

        seen_ids.add(
            document_id
        )

    return output


def get_files_in_order(
    google_docs,
    ordered_document_ids,
):

    lookup = {
        str(file["id"]): file
        for file in google_docs
    }

    return [
        lookup[document_id]
        for document_id
        in ordered_document_ids
        if document_id in lookup
    ]


def compile_selected_pdf(
    selected_files,
):

    if not selected_files:
        return None

    writer = PdfWriter()

    for file in selected_files:

        pdf_data = (
            export_google_doc_as_pdf(
                file["id"]
            )
        )

        reader = PdfReader(
            BytesIO(pdf_data)
        )

        for page in reader.pages:
            writer.add_page(page)

    output = BytesIO()

    writer.write(output)

    output.seek(0)

    return output.getvalue()


@st.cache_data(
    show_spinner=False,
    ttl=300,
)
def compile_pdf_for_download(
    document_ids,
    modified_times,
):

    del modified_times

    selected_files = (
        get_files_in_order(
            google_docs,
            document_ids,
        )
    )

    return compile_selected_pdf(
        selected_files
    )


# ============================================================
# PDF.JS PRESENTATION VIEWER
# ============================================================

def create_pdf_viewer(
    pdf_bytes,
):

    pdf_base64 = base64.b64encode(
        pdf_bytes
    ).decode("ascii")

    return f"""
<!DOCTYPE html>

<html lang="en">

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="
            width=device-width,
            initial-scale=1,
            viewport-fit=cover
        "
    >

    <script
        src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"
    ></script>

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
                Arial,
                sans-serif;
        }}

        #viewer {{
            position: fixed;
            inset: 0;
            width: 100vw;
            height: 100vh;
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
            gap: 7px;
            padding: 7px;
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
            font-weight: 700;
            cursor: pointer;
        }}

        button:hover {{
            background: #e8eaed;
        }}

        button:active {{
            transform: scale(0.96);
        }}

        button:disabled {{
            opacity: 0.4;
            cursor: default;
        }}

        #page-info {{
            min-width: 80px;
            color: white;
            text-align: center;
            white-space: nowrap;
        }}

        #stage {{
            flex: 1 1 auto;
            min-height: 0;
            width: 100%;
            overflow: auto;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 8px;
            background: #525659;
        }}

        #pdf-canvas {{
            display: none;
            margin: auto;
            background: white;
            box-shadow:
                0 3px 14px
                rgba(0, 0, 0, 0.45);
        }}

        #loading {{
            color: white;
            padding: 30px;
            text-align: center;
        }}

        #error {{
            display: none;
            color: white;
            padding: 15px;
            border-radius: 8px;
            background: #b3261e;
        }}

        @media (max-width: 600px) {{

            #toolbar {{
                gap: 4px;
                padding: 6px 3px;
            }}

            button {{
                min-width: 36px;
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
                title="Previous slide"
            >
                ◀
            </button>

            <span id="page-info">
                Loading...
            </span>

            <button
                id="next-button"
                title="Next slide"
            >
                ▶
            </button>

            <button
                id="zoom-out-button"
                title="Zoom out"
            >
                −
            </button>

            <button
                id="fit-button"
                title="Fit slide"
            >
                Fit
            </button>

            <button
                id="zoom-in-button"
                title="Zoom in"
            >
                +
            </button>

            <button
                id="fullscreen-button"
                title="Fullscreen"
            >
                ⛶
            </button>

        </div>

        <div id="stage">

            <div id="loading">
                Loading presentation...
            </div>

            <div id="error">
                The presentation could not be loaded.
            </div>

            <canvas id="pdf-canvas">
            </canvas>

        </div>

    </div>

    <script>

        pdfjsLib.GlobalWorkerOptions.workerSrc =
            "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";


        const rawPdfData =
            window.atob(
                "{pdf_base64}"
            );


        const pdfData =
            new Uint8Array(
                rawPdfData.length
            );


        for (
            let index = 0;
            index < rawPdfData.length;
            index++
        ) {{
            pdfData[index] =
                rawPdfData.charCodeAt(
                    index
                );
        }}


        const viewer =
            document.getElementById(
                "viewer"
            );


        const stage =
            document.getElementById(
                "stage"
            );


        const canvas =
            document.getElementById(
                "pdf-canvas"
            );


        const context =
            canvas.getContext(
                "2d"
            );


        const pageInfo =
            document.getElementById(
                "page-info"
            );


        const previousButton =
            document.getElementById(
                "previous-button"
            );


        const nextButton =
            document.getElementById(
                "next-button"
            );


        const loadingMessage =
            document.getElementById(
                "loading"
            );


        const errorMessage =
            document.getElementById(
                "error"
            );


        let pdfDocument = null;

        let currentPage = 1;

        let fitScale = 1;

        let zoomFactor = 1;

        let renderTask = null;

        let renderVersion = 0;


        async function calculateFitScale(
            page
        ) {{

            const viewport =
                page.getViewport({{
                    scale: 1
                }});


            const availableWidth =
                Math.max(
                    stage.clientWidth - 16,
                    100
                );


            const availableHeight =
                Math.max(
                    stage.clientHeight - 16,
                    100
                );


            return Math.min(
                availableWidth
                    / viewport.width,
                availableHeight
                    / viewport.height
            );

        }}


        async function renderPage(
            recalculateFit = false
        ) {{

            if (!pdfDocument) {{
                return;
            }}


            const currentRenderVersion =
                ++renderVersion;


            if (renderTask) {{

                try {{
                    renderTask.cancel();
                }}

                catch (error) {{
                    console.log(error);
                }}

            }}


            try {{

                const page =
                    await pdfDocument.getPage(
                        currentPage
                    );


                if (
                    currentRenderVersion
                    !== renderVersion
                ) {{
                    return;
                }}


                if (recalculateFit) {{

                    fitScale =
                        await calculateFitScale(
                            page
                        );

                }}


                const viewport =
                    page.getViewport({{
                        scale:
                            fitScale
                            * zoomFactor
                    }});


                const outputScale =
                    window.devicePixelRatio
                    || 1;


                canvas.width =
                    Math.floor(
                        viewport.width
                        * outputScale
                    );


                canvas.height =
                    Math.floor(
                        viewport.height
                        * outputScale
                    );


                canvas.style.width =
                    Math.floor(
                        viewport.width
                    )
                    + "px";


                canvas.style.height =
                    Math.floor(
                        viewport.height
                    )
                    + "px";


                const transform =
                    outputScale === 1
                        ? null
                        : [
                            outputScale,
                            0,
                            0,
                            outputScale,
                            0,
                            0
                        ];


                renderTask =
                    page.render({{
                        canvasContext:
                            context,
                        viewport:
                            viewport,
                        transform:
                            transform
                    }});


                await renderTask.promise;


                if (
                    currentRenderVersion
                    !== renderVersion
                ) {{
                    return;
                }}


                canvas.style.display =
                    "block";


                loadingMessage.style.display =
                    "none";


                errorMessage.style.display =
                    "none";


                pageInfo.textContent =
                    currentPage
                    + " / "
                    + pdfDocument.numPages;


                previousButton.disabled =
                    currentPage <= 1;


                nextButton.disabled =
                    currentPage
                    >= pdfDocument.numPages;


                stage.scrollTop = 0;
                stage.scrollLeft = 0;

            }}

            catch (error) {{

                if (
                    error
                    && error.name
                    === "RenderingCancelledException"
                ) {{
                    return;
                }}


                console.error(error);


                loadingMessage.style.display =
                    "none";


                errorMessage.style.display =
                    "block";


                pageInfo.textContent =
                    "Error";

            }}

            finally {{
                renderTask = null;
            }}

        }}


        function movePage(
            difference
        ) {{

            if (!pdfDocument) {{
                return;
            }}


            const targetPage =
                Math.min(
                    Math.max(
                        currentPage
                        + difference,
                        1
                    ),
                    pdfDocument.numPages
                );


            if (
                targetPage
                === currentPage
            ) {{
                return;
            }}


            currentPage =
                targetPage;


            renderPage(false);

        }}


        previousButton.onclick =
            function() {{
                movePage(-1);
            }};


        nextButton.onclick =
            function() {{
                movePage(1);
            }};


        document
            .getElementById(
                "zoom-in-button"
            )
            .onclick =
                function() {{

                    zoomFactor =
                        Math.min(
                            zoomFactor
                            + 0.2,
                            3
                        );


                    renderPage(false);

                }};


        document
            .getElementById(
                "zoom-out-button"
            )
            .onclick =
                function() {{

                    zoomFactor =
                        Math.max(
                            zoomFactor
                            - 0.2,
                            0.4
                        );


                    renderPage(false);

                }};


        document
            .getElementById(
                "fit-button"
            )
            .onclick =
                function() {{

                    zoomFactor = 1;

                    renderPage(true);

                }};


        document
            .getElementById(
                "fullscreen-button"
            )
            .onclick =
                async function() {{

                    try {{

                        if (
                            document.fullscreenElement
                        ) {{

                            await document
                                .exitFullscreen();

                        }}

                        else {{

                            await viewer
                                .requestFullscreen();

                        }}

                    }}

                    catch (error) {{
                        console.error(error);
                    }}

                }};


        document.addEventListener(
            "keydown",
            function(event) {{

                if (
                    event.key
                    === "ArrowRight"
                    || event.key
                    === "PageDown"
                    || event.key
                    === " "
                ) {{

                    event.preventDefault();

                    movePage(1);

                }}


                if (
                    event.key
                    === "ArrowLeft"
                    || event.key
                    === "PageUp"
                ) {{

                    event.preventDefault();

                    movePage(-1);

                }}

            }
        );


        let touchStartX = null;


        stage.addEventListener(
            "touchstart",
            function(event) {{

                if (
                    event.touches.length
                    === 1
                ) {{

                    touchStartX =
                        event
                        .touches[0]
                        .clientX;

                }}

            }},
            {{
                passive: true
            }}
        );


        stage.addEventListener(
            "touchend",
            function(event) {{

                if (
                    touchStartX === null
                    || event
                        .changedTouches
                        .length !== 1
                ) {{
                    return;
                }}


                const touchEndX =
                    event
                    .changedTouches[0]
                    .clientX;


                const difference =
                    touchEndX
                    - touchStartX;


                if (
                    Math.abs(
                        difference
                    ) > 70
                ) {{

                    movePage(
                        difference < 0
                            ? 1
                            : -1
                    );

                }}


                touchStartX = null;

            }},
            {{
                passive: true
            }}
        );


        let resizeTimer = null;


        function refitPage() {{

            clearTimeout(
                resizeTimer
            );


            resizeTimer =
                setTimeout(
                    function() {{

                        zoomFactor = 1;

                        renderPage(true);

                    }},
                    200
                );

        }}


        window.addEventListener(
            "resize",
            refitPage
        );


        document.addEventListener(
            "fullscreenchange",
            function() {{

                setTimeout(
                    function() {{

                        zoomFactor = 1;

                        renderPage(true);

                    }},
                    150
                );

            }
        );


        async function loadPresentation() {{

            try {{

                const loadingTask =
                    pdfjsLib.getDocument({{
                        data:
                            pdfData
                    }});


                pdfDocument =
                    await loadingTask.promise;


                await renderPage(true);

            }}

            catch (error) {{

                console.error(error);


                loadingMessage.style.display =
                    "none";


                errorMessage.style.display =
                    "block";


                pageInfo.textContent =
                    "Error";

            }}

        }}


        loadPresentation();

    </script>

</body>

</html>
"""


# ============================================================
# LOAD GOOGLE DRIVE DOCUMENTS
# ============================================================

try:

    google_docs = get_google_docs()

except Exception as error:

    st.error(
        "Could not load Google Docs "
        "from the configured Drive folder."
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

        shared_order = (
            clean_document_order(
                get_shared_order(),
                file_by_id,
            )
        )

        selected_files = (
            get_files_in_order(
                google_docs,
                shared_order,
            )
        )

    except Exception as error:

        st.error(
            "Could not load the "
            "shared presentation."
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
                    Return to KerkSlides and save a
                    shared presentation first.
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

            pdf_bytes = (
                compile_selected_pdf(
                    selected_files
                )
            )

    except Exception as error:

        st.error(
            "Could not compile "
            "the presentation."
        )

        st.exception(error)
        st.stop()


    if not pdf_bytes:

        st.error(
            "The presentation PDF "
            "could not be created."
        )

        st.stop()


    components.html(
        create_pdf_viewer(
            pdf_bytes
        ),
        height=900,
        scrolling=False,
    )

    st.stop()


# ============================================================
# NORMAL APPLICATION STATE
# ============================================================

try:

    shared_order = (
        clean_document_order(
            get_shared_order(),
            file_by_id,
        )
    )

except Exception as error:

    st.error(
        "Could not read the saved "
        "presentation from Google Sheets."
    )

    st.exception(error)
    st.stop()


if "draft_order" not in st.session_state:

    st.session_state.draft_order = (
        shared_order.copy()
    )


if "last_saved_order" not in st.session_state:

    st.session_state.last_saved_order = (
        shared_order.copy()
    )


if "sorter_version" not in st.session_state:

    st.session_state.sorter_version = 0


if "save_message" not in st.session_state:

    st.session_state.save_message = None


st.session_state.draft_order = (
    clean_document_order(
        st.session_state.draft_order,
        file_by_id,
    )
)


def refresh_sorter():

    st.session_state.sorter_version += 1


# ============================================================
# HEADER
# ============================================================

header_left, header_right = (
    st.columns(
        [5, 1]
    )
)


with header_left:

    st.title(
        "⛪ KerkSlides"
    )

    st.caption(
        "Create, order, download, and share "
        "one synchronized presentation."
    )


with header_right:

    st.write("")

    refresh_clicked = st.button(
        "🔄 Refresh",
        use_container_width=True,
    )


    if refresh_clicked:

        try:

            get_google_docs.clear()
            st.cache_data.clear()

            refreshed_order = (
                clean_document_order(
                    get_shared_order(),
                    file_by_id,
                )
            )

            st.session_state.draft_order = (
                refreshed_order.copy()
            )

            st.session_state.last_saved_order = (
                refreshed_order.copy()
            )

            st.session_state.save_message = None

            refresh_sorter()

            st.rerun()

        except Exception as error:

            st.error(
                "Could not refresh "
                "the presentation."
            )

            st.exception(error)


st.divider()


# ============================================================
# MAIN LAYOUT
# ============================================================

workspace_column, presentation_column = (
    st.columns(
        [2.1, 1],
        gap="large",
    )
)


# ============================================================
# LEFT SIDE
# ============================================================

with workspace_column:

    with st.container(
        border=True
    ):

        st.subheader(
            "Build presentation"
        )

        st.caption(
            "Add documents and drag them "
            "into the correct order."
        )


        available_document_ids = [

            str(file["id"])

            for file in google_docs

            if str(file["id"])
            not in st.session_state.draft_order

        ]


        if available_document_ids:

            dropdown_column, add_column = (
                st.columns(
                    [4, 1]
                )
            )


            with dropdown_column:

                selected_document_id = (
                    st.selectbox(
                        "Document",
                        options=(
                            available_document_ids
                        ),
                        format_func=(
                            lambda document_id:
                            file_by_id[
                                document_id
                            ]["name"]
                        ),
                        label_visibility=(
                            "collapsed"
                        ),
                        placeholder=(
                            "Choose a document"
                        ),
                        key=(
                            "add_document_dropdown"
                        ),
                    )
                )


            with add_column:

                add_clicked = st.button(
                    "➕ Add",
                    use_container_width=True,
                )


            if (
                add_clicked
                and selected_document_id
            ):

                if (
                    selected_document_id
                    not in
                    st.session_state.draft_order
                ):

                    st.session_state.draft_order.append(
                        selected_document_id
                    )

                    st.session_state.save_message = None

                    refresh_sorter()

                    st.rerun()


        else:

            st.info(
                "All available Google Docs "
                "have already been added."
            )


        st.divider()


        # ----------------------------------------------------
        # SORT DOCUMENTS
        # ----------------------------------------------------

        st.markdown(
            "#### Presentation order"
        )


        if not st.session_state.draft_order:

            st.info(
                "No documents have been added yet."
            )


        else:

            sortable_labels = []
            label_to_id = {}


            for position, document_id in enumerate(
                st.session_state.draft_order,
                start=1,
            ):

                document_name = (
                    file_by_id[
                        document_id
                    ]["name"]
                )

                label = (
                    f"{position}. "
                    f"{document_name} "
                    f"[{document_id}]"
                )

                sortable_labels.append(
                    label
                )

                label_to_id[label] = (
                    document_id
                )


            reordered_labels = (
                sort_items(
                    sortable_labels,
                    direction="vertical",
                    key=(
                        "presentation_order_sorter_"
                        f"{st.session_state.sorter_version}"
                    ),
                )
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

                st.session_state.save_message = None


            # ------------------------------------------------
            # REMOVE DOCUMENT
            # ------------------------------------------------

            st.markdown(
                "##### Remove document"
            )


            remove_column, remove_button_column = (
                st.columns(
                    [4, 1]
                )
            )


            with remove_column:

                document_to_remove = (
                    st.selectbox(
                        "Remove document",
                        options=(
                            st.session_state
                            .draft_order
                        ),
                        format_func=(
                            lambda document_id:
                            file_by_id[
                                document_id
                            ]["name"]
                        ),
                        label_visibility=(
                            "collapsed"
                        ),
                        key=(
                            "remove_document_dropdown"
                        ),
                    )
                )


            with remove_button_column:

                remove_clicked = st.button(
                    "🗑️ Remove",
                    use_container_width=True,
                )


            if (
                remove_clicked
                and document_to_remove
            ):

                st.session_state.draft_order = [

                    document_id

                    for document_id
                    in st.session_state.draft_order

                    if document_id
                    != document_to_remove

                ]

                st.session_state.save_message = None

                refresh_sorter()

                st.rerun()


        # ----------------------------------------------------
        # SAVE AND RESET
        # ----------------------------------------------------

        st.divider()


        save_column, reset_column = (
            st.columns(
                [2, 1]
            )
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
            )


        if save_clicked:

            try:

                current_order = (
                    clean_document_order(
                        st.session_state.draft_order,
                        file_by_id,
                    )
                )


                with st.spinner(
                    "Saving shared presentation..."
                ):

                    saved_order = (
                        save_shared_order(
                            google_docs,
                            current_order,
                        )
                    )


                st.session_state.draft_order = (
                    saved_order.copy()
                )

                st.session_state.last_saved_order = (
                    saved_order.copy()
                )

                st.session_state.save_message = (
                    "Shared presentation "
                    "saved successfully."
                )

                st.cache_data.clear()

                refresh_sorter()

                st.rerun()


            except Exception as error:

                st.error(
                    "Could not save the "
                    "shared presentation."
                )

                st.exception(error)


        if reset_clicked:

            try:

                restored_order = (
                    clean_document_order(
                        get_shared_order(),
                        file_by_id,
                    )
                )

                st.session_state.draft_order = (
                    restored_order.copy()
                )

                st.session_state.last_saved_order = (
                    restored_order.copy()
                )

                st.session_state.save_message = None

                refresh_sorter()

                st.rerun()


            except Exception as error:

                st.error(
                    "Could not restore the "
                    "shared presentation."
                )

                st.exception(error)


        if st.session_state.save_message:

            st.success(
                st.session_state.save_message
            )


# ============================================================
# RIGHT SIDE
# ============================================================

with presentation_column:

    with st.container(
        border=True
    ):

        st.subheader(
            "Presentation order"
        )


        draft_files = (
            get_files_in_order(
                google_docs,
                st.session_state.draft_order,
            )
        )


        if draft_files:

            order_items_html = "".join(

                (
                    '<div class="presentation-order-item">'
                    f"<strong>{index}.</strong> "
                    f"{html.escape(file['name'])}"
                    "</div>"
                )

                for index, file in enumerate(
                    draft_files,
                    start=1,
                )

            )


            st.markdown(
                (
                    '<div class="presentation-order-box">'
                    f"{order_items_html}"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


        else:

            st.info(
                "No documents have been added."
            )


        # ----------------------------------------------------
        # DOWNLOAD PDF
        # ----------------------------------------------------

        if draft_files:

            try:

                document_ids = tuple(
                    st.session_state.draft_order
                )


                modified_times = tuple(

                    str(
                        file_by_id[
                            document_id
                        ].get(
                            "modifiedTime",
                            "",
                        )
                    )

                    for document_id
                    in document_ids

                )


                with st.spinner(
                    "Preparing download..."
                ):

                    download_pdf = (
                        compile_pdf_for_download(
                            document_ids,
                            modified_times,
                        )
                    )


                st.download_button(
                    "⬇️ Download combined PDF",
                    data=download_pdf,
                    file_name=OUTPUT_FILE_NAME,
                    mime="application/pdf",
                    use_container_width=True,
                )


            except Exception as error:

                st.error(
                    "The combined PDF "
                    "could not be prepared."
                )

                with st.expander(
                    "View technical error"
                ):

                    st.exception(error)


        else:

            st.download_button(
                "⬇️ Download combined PDF",
                data=b"",
                file_name=OUTPUT_FILE_NAME,
                mime="application/pdf",
                disabled=True,
                use_container_width=True,
            )


        # ----------------------------------------------------
        # SHOW PRESENTATION
        # ----------------------------------------------------

        if st.session_state.last_saved_order:

            st.markdown(
                """
                ?view=presentation
                    🎥 Show presentation
                </a>
                """,
                unsafe_allow_html=True,
            )

            st.caption(
                "Opens the last saved shared "
                "presentation in a new tab."
            )


        else:

            st.button(
                "🎥 Show presentation",
                disabled=True,
                use_container_width=True,
            )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "KerkSlides • Shared through Google Sheets • "
    "Documents loaded from Google Drive"
)
