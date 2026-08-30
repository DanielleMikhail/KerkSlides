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
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("📄 KerkSlides")


# ============================================================
# CONFIGURATION
# ============================================================


FOLDER_ID = "1q-5HeICSq5zBoQAEDb_PNA3iMXbgrNBn"
SPREADSHEET_ID = "1f4EFf5HeWCUtPtqYtsoooOAXpibKiuXEoWU0CHAOjWQ"



# ============================================================
# GOOGLE CREDENTIALS
# ============================================================

credentials = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/spreadsheets"
    ]
)


# ============================================================
# GOOGLE DRIVE
# ============================================================

drive_service = build(
    "drive",
    "v3",
    credentials=credentials
)


# ============================================================
# GOOGLE SHEETS
# ============================================================

gc = gspread.authorize(credentials)

sheet = gc.open_by_key(
    SPREADSHEET_ID
).sheet1


# ============================================================
# GET GOOGLE DOCS
# ============================================================

results = drive_service.files().list(
    q=f"'{FOLDER_ID}' in parents "
      f"and mimeType='application/vnd.google-apps.document' "
      f"and trashed=false",
    fields="files(id,name)"
).execute()

google_docs = results.get("files", [])


# ============================================================
# TABS
# ============================================================

tab_select, tab_preview = st.tabs(
    [
        "📁 Select documents",
        "👀 Preview"
    ]
)


# ============================================================
# TAB 1 — SELECT DOCUMENTS
# ============================================================

with tab_select:

    st.header("Select documents")

    if not google_docs:

        st.warning(
            "No Google Docs found in this folder."
        )

    else:

        st.write(
            f"Found **{len(google_docs)} documents**."
        )


        # ----------------------------------------------------
        # READ CURRENT SHARED SELECTION
        # ----------------------------------------------------

        shared_rows = sheet.get_all_records()

        shared_selection = {
            str(row["document_id"]):
                str(row["selected"]).upper() == "TRUE"
            for row in shared_rows
            if row.get("document_id")
        }


        current_selection = []


        # ----------------------------------------------------
        # CHECKBOXES
        # ----------------------------------------------------

        for file in google_docs:

            selected = st.checkbox(
                file["name"],
                value=shared_selection.get(
                    file["id"],
                    False
                ),
                key=f"checkbox_{file['id']}"
            )

            if selected:

                current_selection.append(
                    file["id"]
                )


        # ----------------------------------------------------
        # SAVE SHARED SELECTION
        # ----------------------------------------------------

        st.divider()

        if st.button(
            "💾 Update shared selection",
            type="primary",
            use_container_width=True
        ):

            rows = sheet.get_all_records()

            row_by_id = {
                str(row["document_id"]):
                    index + 2
                for index, row
                in enumerate(rows)
                if row.get("document_id")
            }


            for file in google_docs:

                row_number = row_by_id.get(
                    file["id"]
                )

                if row_number:

                    selected_value = (
                        "TRUE"
                        if file["id"]
                        in current_selection
                        else "FALSE"
                    )

                    sheet.update_cell(
                        row_number,
                        3,
                        selected_value
                    )


            st.success(
                "Shared selection updated! ✅"
            )

            st.rerun()


# ============================================================
# TAB 2 — PREVIEW
# ============================================================

with tab_preview:

    st.header("👀 Combined document")


    # --------------------------------------------------------
    # READ SHARED SELECTION
    # --------------------------------------------------------

    shared_rows = sheet.get_all_records()


    shared_selection = {
        str(row["document_id"]):
            str(row["selected"]).upper() == "TRUE"
        for row in shared_rows
        if row.get("document_id")
    }


    # --------------------------------------------------------
    # SELECTED DOCUMENTS
    # --------------------------------------------------------

    selected_files = [
        file
        for file in google_docs
        if shared_selection.get(
            file["id"],
            False
        )
    ]


    if not selected_files:

        st.info(
            "No documents have been selected yet."
        )


    else:

        st.write(
            f"**{len(selected_files)} documents** "
            "selected."
        )


        # ====================================================
        # CREATE COMBINED PDF
        # ====================================================

        pdf_writer = PdfWriter()


        with st.spinner(
            "Creating combined document..."
        ):

            for file in selected_files:

                request = drive_service.files().export_media(
                    fileId=file["id"],
                    mimeType="application/pdf"
                )

                pdf_data = request.execute()


                pdf_reader = PdfReader(
                    BytesIO(pdf_data)
                )


                for page in pdf_reader.pages:

                    pdf_writer.add_page(
                        page
                    )


        # ----------------------------------------------------
        # CREATE PDF BYTES
        # ----------------------------------------------------

        combined_pdf = BytesIO()

        pdf_writer.write(
            combined_pdf
        )

        combined_pdf.seek(0)

        pdf_bytes = combined_pdf.getvalue()


        # ====================================================
        # DOWNLOAD
        # ====================================================

        st.download_button(
            "⬇️ Download combined PDF",
            data=pdf_bytes,
            file_name="KerkSlides_Compiled.pdf",
            mime="application/pdf",
            use_container_width=True
        )


        st.divider()


        st.subheader(
            "📖 Document preview"
        )


        # ====================================================
        # BASE64
        # ====================================================

        pdf_base64 = base64.b64encode(
            pdf_bytes
        ).decode("utf-8")


        # ====================================================
        # MOBILE FRIENDLY PDF VIEWER
        # ====================================================

        viewer_html = f"""

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
      content="width=device-width,
               initial-scale=1.0,
               maximum-scale=1.0,
               user-scalable=yes">


<script src="
https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js
">
</script>


<style>

/* ========================================================
   BASIC
======================================================== */

* {{
    box-sizing: border-box;
}}


html,
body {{

    margin: 0;

    padding: 0;

    width: 100%;

    height: 100%;

    overflow: hidden;

    background: #525659;

}}


/* ========================================================
   VIEWER
======================================================== */

#viewer {{

    width: 100%;

    height: 100vh;

    height: 100dvh;

    background: #525659;

    display: flex;

    flex-direction: column;

    position: relative;

}}


/* ========================================================
   TOOLBAR
======================================================== */

#toolbar {{

    height: 52px;

    min-height: 52px;

    background: #292b2d;

    display: flex;

    align-items: center;

    justify-content: center;

    gap: 6px;

    padding: 6px;

    z-index: 20;

}}


button {{

    border: none;

    border-radius: 6px;

    background: white;

    padding: 8px 12px;

    font-size: 15px;

    cursor: pointer;

    white-space: nowrap;

}}


button:active {{

    transform: scale(0.95);

}}


#page-info {{

    color: white;

    font-size: 14px;

    margin: 0 5px;

}}


/* ========================================================
   PDF AREA
======================================================== */

#pdf-container {{

    flex: 1;

    overflow-y: auto;

    overflow-x: auto;

    -webkit-overflow-scrolling: touch;

    padding: 15px 8px 40px 8px;

    text-align: center;

}}


/* ========================================================
   PDF PAGES
======================================================== */

.page {{

    display: block;

    margin: 0 auto 18px auto;

    background: white;

    box-shadow:
        0 2px 10px
        rgba(0,0,0,0.4);

    max-width: none;

}}


/* ========================================================
   MOBILE
======================================================== */

@media (max-width: 600px) {{

    #toolbar {{

        height: 48px;

        min-height: 48px;

        gap: 4px;

        padding: 4px;

    }}


    button {{

        padding: 7px 9px;

        font-size: 13px;

    }}


    #page-info {{

        font-size: 12px;

        margin: 0 3px;

    }}


    #pdf-container {{

        padding: 8px 3px 30px 3px;

    }}

}}


/* ========================================================
   FULLSCREEN MODE
======================================================== */

#viewer:fullscreen {{

    width: 100vw;

    height: 100vh;

}}


#viewer:-webkit-full-screen {{

    width: 100vw;

    height: 100vh;

}}


</style>

</head>


<body>


<div id="viewer">


    <!-- ================================================
         TOOLBAR
    ================================================= -->


    <div id="toolbar">


        <button onclick="zoomOut()">
            −
        </button>


        <button onclick="zoomIn()">
            +
        </button>


        <button onclick="resetZoom()">
            100%
        </button>


        <span id="page-info">
            Loading...
        </span>


        <button onclick="goFullscreen()">
            ⛶
        </button>


    </div>


    <!-- ================================================
         PDF
    ================================================= -->


    <div id="pdf-container">

        <div
            style="
                color:white;
                padding:30px;
                font-size:16px;
            "
        >

            Loading document...

        </div>

    </div>


</div>


<script>


/* ========================================================
   PDF DATA
======================================================== */

const pdfData =
    atob("{pdf_base64}");


let pdfDoc = null;

let scale = 1.0;

let rendering = false;


/* ========================================================
   LOAD PDF
======================================================== */

async function loadPDF() {{

    try {{

        const loadingTask =
            pdfjsLib.getDocument({{
                data: Uint8Array.from(
                    pdfData,
                    c => c.charCodeAt(0)
                )
            }});


        pdfDoc =
            await loadingTask.promise;


        document.getElementById(
            "page-info"
        ).innerText =
            pdfDoc.numPages +
            " pages";


        renderAllPages();


    }} catch (error) {{

        document.getElementById(
            "page-info"
        ).innerText =
            "Error loading PDF";


        console.error(error);

    }}

}}


/* ========================================================
   RENDER ALL PAGES
======================================================== */

async function renderAllPages() {{

    if (
        rendering ||
        !pdfDoc
    ) {{

        return;

    }}


    rendering = true;


    const container =
        document.getElementById(
            "pdf-container"
        );


    container.innerHTML = "";


    for (
        let pageNumber = 1;
        pageNumber <= pdfDoc.numPages;
        pageNumber++
    ) {{

        const page =
            await pdfDoc.getPage(
                pageNumber
            );


        const viewport =
            page.getViewport({{
                scale: scale
            }});


        const canvas =
            document.createElement(
                "canvas"
            );


        canvas.className =
            "page";


        canvas.width =
            viewport.width;


        canvas.height =
            viewport.height;


        container.appendChild(
            canvas
        );


        const context =
            canvas.getContext(
                "2d"
            );


        await page.render({{

            canvasContext:
                context,

            viewport:
                viewport

        }}).promise;

    }}


    rendering = false;

}}


/* ========================================================
   ZOOM
======================================================== */

function zoomIn() {{

    scale += 0.2;

    renderAllPages();

}}


function zoomOut() {{

    if (scale > 0.4) {{

        scale -= 0.2;

        renderAllPages();

    }}

}}


function resetZoom() {{

    scale = 1.0;

    renderAllPages();

}}


/* ========================================================
   FULLSCREEN
======================================================== */

function goFullscreen() {{

    const viewer =
        document.getElementById(
            "viewer"
        );


    /* Already fullscreen */

    if (
        document.fullscreenElement ||
        document.webkitFullscreenElement
    ) {{

        if (
            document.exitFullscreen
        ) {{

            document.exitFullscreen();

        }}

        else if (
            document.webkitExitFullscreen
        ) {{

            document.webkitExitFullscreen();

        }}

        return;

    }}


    /* Desktop Chrome */

    if (
        viewer.requestFullscreen
    ) {{

        viewer.requestFullscreen();

        return;

    }}


    /* Safari */

    if (
        viewer.webkitRequestFullscreen
    ) {{

        viewer.webkitRequestFullscreen();

        return;

    }}


    /* iPhone/iPad fallback */

    document.body.classList.add(
        "mobile-fullscreen"
    );

}}


/* ========================================================
   START
======================================================== */

loadPDF();


</script>


</body>

</html>

"""


        # ====================================================
        # DISPLAY VIEWER
        # ====================================================

        components.html(
            viewer_html,
            height=750,
            scrolling=False
        )

