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

presentation_mode = st.query_params.get("view", "") == "presentation"


# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="KerkSlides Presentation" if presentation_mode else "KerkSlides",
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
    st.title("⛪ KerkSlides")


# ============================================================
# CONFIGURATION
# ============================================================

SOURCE_FOLDER_ID = "1q-5HeICSq5zBoQAEDb_PNA3iMXbgrNBn"
SPREADSHEET_ID = "1f4EFf5HeWCUtPtqYtsoooOAXpibKiuXEoWU0CHAOjWQ"
OUTPUT_FILE_NAME = "KerkSlides_Compiled.pdf"


# ============================================================
# GOOGLE CONNECTION
# ============================================================

try:
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ],
    )

    drive_service = build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    sheet = gspread.authorize(credentials).open_by_key(SPREADSHEET_ID).sheet1

except Exception as error:
    st.error("Could not connect to Google Drive or Google Sheets.")
    st.exception(error)
    st.stop()


# ============================================================
# GOOGLE DRIVE AND SHEET FUNCTIONS
# ============================================================

@st.cache_data(show_spinner=False, ttl=60)
def get_google_docs():
    """Retrieve all Google Docs from the configured folder."""

    files = []
    page_token = None

    while True:
        result = drive_service.files().list(
            q=(
                f"'{SOURCE_FOLDER_ID}' in parents "
                "and mimeType='application/vnd.google-apps.document' "
                "and trashed=false"
            ),
            fields="nextPageToken, files(id, name, modifiedTime)",
            orderBy="name",
            pageToken=page_token,
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        files.extend(result.get("files", []))
        page_token = result.get("nextPageToken")

        if not page_token:
            return files


def ensure_sheet_headers():
    """Ensure the Google Sheet has the expected three columns."""

    expected_headers = [
        "document_id",
        "document_name",
        "selected",
    ]

    if sheet.row_values(1) != expected_headers:
        sheet.update(
            range_name="A1:C1",
            values=[expected_headers],
            value_input_option="RAW",
        )


def get_shared_selection():
    """Read the saved central selection from Google Sheets."""

    rows = sheet.get_all_records()

    return {
        str(row["document_id"]): (
            str(row.get("selected", "")).strip().upper()
            in {"TRUE", "1", "YES"}
        )
        for row in rows
        if row.get("document_id")
    }


def save_shared_selection(google_docs, current_selection):
    """Save the complete document selection in a single Sheet update."""

    selected_ids = set(map(str, current_selection))

    values = [
        [
            "document_id",
            "document_name",
            "selected",
        ]
    ]

    for file in google_docs:
        document_id = str(file["id"])

        values.append(
            [
                document_id,
                str(file["name"]),
                "TRUE" if document_id in selected_ids else "FALSE",
            ]
        )

    required_rows = max(len(values), 2)

    if sheet.row_count < required_rows:
        sheet.add_rows(required_rows - sheet.row_count)

    sheet.batch_clear([f"A1:C{sheet.row_count}"])

    sheet.update(
        range_name=f"A1:C{len(values)}",
        values=values,
        value_input_option="RAW",
    )


def get_selected_files(google_docs, shared_selection):
    """Return the selected Drive files in Drive name order."""

    return [
        file
        for file in google_docs
        if shared_selection.get(str(file["id"]), False)
    ]


def export_google_doc_as_pdf(document_id):
    """Export one Google Doc as PDF bytes."""

    return drive_service.files().export_media(
        fileId=document_id,
        mimeType="application/pdf",
    ).execute()


def compile_selected_pdf(selected_files):
    """Export the selected Docs and combine them into one PDF."""

    if not selected_files:
        return None

    writer = PdfWriter()

    for file in selected_files:
        pdf_data = export_google_doc_as_pdf(file["id"])
        reader = PdfReader(BytesIO(pdf_data))

        for page in reader.pages:
            writer.add_page(page)

    combined_pdf = BytesIO()
    writer.write(combined_pdf)
    combined_pdf.seek(0)

    return combined_pdf.getvalue()


@st.cache_data(show_spinner=False, ttl=300)
def compile_pdf_cached(document_ids, modified_times):
    """Cache compiled PDFs until a selected source document changes."""

    del modified_times

    file_by_id = {
        str(file["id"]): file
        for file in google_docs
    }

    selected_files = [
        file_by_id[document_id]
        for document_id in document_ids
        if document_id in file_by_id
    ]

    return compile_selected_pdf(selected_files)


# ============================================================
# SCROLLABLE PDF.JS VIEWER
# ============================================================


def create_scrollable_pdf_viewer(pdf_bytes):
    """
    Create a continuous vertical PDF viewer.

    All pages are rendered underneath one another. The user scrolls
    down and up rather than using previous/next-page navigation.
    """

    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1, viewport-fit=cover"
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
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}

        #viewer {{
            position: fixed;
            inset: 0;
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
            gap: 8px;
            padding: 7px 10px;
            padding-top: max(7px, env(safe-area-inset-top));
            background: #292b2d;
            color: white;
            z-index: 10;
        }}

        #page-status {{
            min-width: 110px;
            text-align: center;
            font-size: 14px;
            font-weight: 600;
        }}

        button {{
            min-width: 42px;
            min-height: 38px;
            border: none;
            border-radius: 8px;
            padding: 8px 12px;
            background: white;
            color: #202124;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            touch-action: manipulation;
        }}

        button:hover {{
            background: #e8eaed;
        }}

        button:active {{
            transform: scale(0.97);
        }}

        #scroll-container {{
            flex: 1 1 auto;
            min-height: 0;
            overflow-x: auto;
            overflow-y: scroll;
            -webkit-overflow-scrolling: touch;
            overscroll-behavior: contain;
            scroll-behavior: smooth;
            padding: 14px 10px 28px;
            background: #525659;
        }}

        #pages {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 14px;
            min-width: 100%;
        }}

        .pdf-page {{
            display: block;
            background: white;
            box-shadow: 0 3px 14px rgba(0, 0, 0, 0.45);
        }}

        #loading {{
            padding: 45px 20px;
            color: white;
            text-align: center;
            font-size: 16px;
        }}

        #error {{
            display: none;
            max-width: 560px;
            margin: 30px auto;
            padding: 15px;
            border-radius: 8px;
            background: #b3261e;
            color: white;
            text-align: center;
        }}

        @media (max-width: 600px) {{
            #toolbar {{
                min-height: 50px;
                gap: 5px;
                padding-left: 5px;
                padding-right: 5px;
            }}

            button {{
                min-width: 37px;
                min-height: 36px;
                padding: 7px 9px;
                font-size: 13px;
            }}

            #page-status {{
                min-width: 88px;
                font-size: 12px;
            }}

            #scroll-container {{
                padding: 8px 5px 20px;
            }}

            #pages {{
                gap: 8px;
            }}
        }}
    </style>
</head>

<body>
    <div id="viewer">
        <div id="toolbar">
            <button id="zoom-out" aria-label="Zoom out">−</button>
            <button id="fit-width" aria-label="Fit width">Fit width</button>
            <button id="zoom-in" aria-label="Zoom in">+</button>
            <span id="page-status">Loading...</span>
            <button id="fullscreen" aria-label="Fullscreen">⛶</button>
        </div>

        <div id="scroll-container">
            <div id="loading">Loading presentation...</div>
            <div id="error">The presentation could not be loaded.</div>
            <div id="pages"></div>
        </div>
    </div>

    <script>
        pdfjsLib.GlobalWorkerOptions.workerSrc =
            "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

        const encodedPdf = "{pdf_base64}";
        const rawPdf = window.atob(encodedPdf);
        const pdfData = new Uint8Array(rawPdf.length);

        for (let index = 0; index < rawPdf.length; index++) {{
            pdfData[index] = rawPdf.charCodeAt(index);
        }}

        const viewer = document.getElementById("viewer");
        const scrollContainer = document.getElementById("scroll-container");
        const pagesElement = document.getElementById("pages");
        const loadingElement = document.getElementById("loading");
        const errorElement = document.getElementById("error");
        const pageStatus = document.getElementById("page-status");

        let pdfDocument = null;
        let zoomFactor = 1;
        let fitWidthScale = 1;
        let renderVersion = 0;
        let resizeTimer = null;

        function availablePageWidth() {{
            return Math.max(scrollContainer.clientWidth - 24, 120);
        }}

        async function calculateFitWidth() {{
            const firstPage = await pdfDocument.getPage(1);
            const viewport = firstPage.getViewport({{ scale: 1 }});
            return availablePageWidth() / viewport.width;
        }}

        async function renderAllPages(recalculateFit = false) {{
            if (!pdfDocument) {{
                return;
            }}

            const currentVersion = ++renderVersion;

            if (recalculateFit) {{
                fitWidthScale = await calculateFitWidth();
            }}

            pagesElement.innerHTML = "";
            loadingElement.style.display = "block";
            errorElement.style.display = "none";

            const scale = fitWidthScale * zoomFactor;
            const outputScale = window.devicePixelRatio || 1;

            try {{
                for (
                    let pageNumber = 1;
                    pageNumber <= pdfDocument.numPages;
                    pageNumber++
                ) {{
                    if (currentVersion !== renderVersion) {{
                        return;
                    }}

                    pageStatus.textContent =
                        `Rendering ${{pageNumber}} / ${{pdfDocument.numPages}}`;

                    const page = await pdfDocument.getPage(pageNumber);
                    const viewport = page.getViewport({{ scale }});
                    const canvas = document.createElement("canvas");
                    const context = canvas.getContext("2d");

                    canvas.className = "pdf-page";
                    canvas.dataset.pageNumber = pageNumber;
                    canvas.width = Math.floor(viewport.width * outputScale);
                    canvas.height = Math.floor(viewport.height * outputScale);
                    canvas.style.width = Math.floor(viewport.width) + "px";
                    canvas.style.height = Math.floor(viewport.height) + "px";

                    pagesElement.appendChild(canvas);

                    await page.render({{
                        canvasContext: context,
                        viewport,
                        transform:
                            outputScale === 1
                                ? null
                                : [outputScale, 0, 0, outputScale, 0, 0],
                    }}).promise;
                }}

                if (currentVersion === renderVersion) {{
                    loadingElement.style.display = "none";
                    pageStatus.textContent = `${{pdfDocument.numPages}} pages`;
                }}

            }} catch (error) {{
                console.error(error);
                loadingElement.style.display = "none";
                errorElement.style.display = "block";
                pageStatus.textContent = "Error";
            }}
        }}

        document.getElementById("zoom-in").addEventListener("click", function() {{
            zoomFactor = Math.min(zoomFactor + 0.15, 2.5);
            renderAllPages(false);
        }});

        document.getElementById("zoom-out").addEventListener("click", function() {{
            zoomFactor = Math.max(zoomFactor - 0.15, 0.4);
            renderAllPages(false);
        }});

        document.getElementById("fit-width").addEventListener("click", function() {{
            zoomFactor = 1;
            renderAllPages(true);
        }});

        document.getElementById("fullscreen").addEventListener("click", async function() {{
            try {{
                if (document.fullscreenElement) {{
                    await document.exitFullscreen();
                }} else if (viewer.requestFullscreen) {{
                    await viewer.requestFullscreen();
                }} else if (viewer.webkitRequestFullscreen) {{
                    viewer.webkitRequestFullscreen();
                }}
            }} catch (error) {{
                console.error(error);
            }}
        }});

        window.addEventListener("resize", function() {{
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function() {{
                zoomFactor = 1;
                renderAllPages(true);
            }}, 250);
        }});

        document.addEventListener("fullscreenchange", function() {{
            setTimeout(function() {{
                zoomFactor = 1;
                renderAllPages(true);
            }}, 200);
        }});

        async function loadPdf() {{
            try {{
                pdfDocument = await pdfjsLib.getDocument({{
                    data: pdfData,
                }}).promise;

                await renderAllPages(true);

            }} catch (error) {{
                console.error(error);
                loadingElement.style.display = "none";
                errorElement.style.display = "block";
                pageStatus.textContent = "Error";
            }}
        }}

        loadPdf();
    </script>
</body>
</html>
"""


# ============================================================
# INITIALIZE DATA
# ============================================================

try:
    ensure_sheet_headers()
    google_docs = get_google_docs()

except Exception as error:
    st.error("Could not load the Google Docs or prepare the Google Sheet.")
    st.exception(error)
    st.stop()


# ============================================================
# PRESENTATION MODE
# ============================================================

if presentation_mode:
    try:
        shared_selection = get_shared_selection()
        selected_files = get_selected_files(google_docs, shared_selection)

    except Exception as error:
        st.error("Could not load the shared selection.")
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
                    Return to KerkSlides, select documents and save the
                    shared selection first.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.stop()

    try:
        document_ids = tuple(str(file["id"]) for file in selected_files)
        modified_times = tuple(
            str(file.get("modifiedTime", ""))
            for file in selected_files
        )

        with st.spinner("Creating presentation..."):
            pdf_bytes = compile_pdf_cached(document_ids, modified_times)

    except Exception as error:
        st.error("Could not compile the presentation.")
        st.exception(error)
        st.stop()

    if not pdf_bytes:
        st.error("The presentation PDF could not be created.")
        st.stop()

    components.html(
        create_scrollable_pdf_viewer(pdf_bytes),
        height=900,
        scrolling=False,
    )

    st.stop()


# ============================================================
# NORMAL APP
# ============================================================

if st.button("🔄 Refresh documents"):
    get_google_docs.clear()
    st.cache_data.clear()
    st.rerun()


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
        st.warning("No Google Docs were found in the source folder.")

    else:
        st.write(f"Found **{len(google_docs)} documents**.")

        try:
            shared_selection = get_shared_selection()

        except Exception as error:
            st.error("Could not read the current shared selection.")
            st.exception(error)
            st.stop()

        current_selection = []

        for file in google_docs:
            document_id = str(file["id"])

            selected = st.checkbox(
                file["name"],
                value=shared_selection.get(document_id, False),
                key=f"checkbox_{document_id}",
            )

            if selected:
                current_selection.append(document_id)

        st.divider()

        if st.button(
            "💾 Update shared selection",
            type="primary",
            use_container_width=True,
        ):
            try:
                save_shared_selection(google_docs, current_selection)
                st.cache_data.clear()
                st.success("Shared selection updated.")
                st.rerun()

            except Exception as error:
                st.error("Could not update the shared selection.")
                st.exception(error)


# ============================================================
# TAB 2: PREVIEW
# ============================================================

with tab_preview:
    st.header("👀 Combined document")

    try:
        shared_selection = get_shared_selection()
        selected_files = get_selected_files(google_docs, shared_selection)

    except Exception as error:
        st.error("Could not read the shared selection.")
        st.exception(error)
        st.stop()

    if not selected_files:
        st.info(
            "No documents have been selected yet. Select documents in the "
            "first tab and click 'Update shared selection'."
        )

    else:
        st.write(f"**{len(selected_files)} documents** selected.")

        with st.expander("View selected documents"):
            for index, file in enumerate(selected_files, start=1):
                st.write(f"{index}. {file['name']}")

        try:
            document_ids = tuple(str(file["id"]) for file in selected_files)
            modified_times = tuple(
                str(file.get("modifiedTime", ""))
                for file in selected_files
            )

            with st.spinner("Creating combined document..."):
                pdf_bytes = compile_pdf_cached(document_ids, modified_times)

        except Exception as error:
            st.error("Could not export and combine the selected documents.")
            st.exception(error)
            st.stop()

        combined_reader = PdfReader(BytesIO(pdf_bytes))

        st.write(
            f"Combined PDF pages: **{len(combined_reader.pages)}**"
        )

        st.download_button(
            "⬇️ Download combined PDF",
            data=pdf_bytes,
            file_name=OUTPUT_FILE_NAME,
            mime="application/pdf",
            use_container_width=True,
        )

        st.link_button(
            "🎥 Open scrollable presentation",
            "?view=presentation",
            type="primary",
            use_container_width=True,
        )

        st.caption(
            "The presentation opens as one continuous PDF. Scroll down and "
            "up to move between pages."
        )

        st.divider()
        st.subheader("📖 Scrollable document preview")

        components.html(
            create_scrollable_pdf_viewer(pdf_bytes),
            height=800,
            scrolling=False,
        )
