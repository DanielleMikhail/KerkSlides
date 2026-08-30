import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
import gspread
from streamlit_sortables import sort_items
from pypdf import PdfWriter, PdfReader
from io import BytesIO
import base64


# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="KerkSlides",
    page_icon="📄",
    layout="wide"
)

st.title("📄 KerkSlides")


# ============================================================
# CONFIGURATION
# ============================================================

# IMPORTANT:
# Replace this with the ID of your Google Drive folder.
#
# Example:
# https://drive.google.com/drive/folders/ABC123XYZ
#
# Folder ID = ABC123XYZ

FOLDER_ID = "YOUR_ACTUAL_FOLDER_ID"


# Replace this with your Google Sheets Spreadsheet ID.
#
# Example:
# https://docs.google.com/spreadsheets/d/ABC123XYZ/edit
#
# Spreadsheet ID = ABC123XYZ

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
# GET GOOGLE DOCS FROM DRIVE
# ============================================================

results = drive_service.files().list(
    q=f"'{FOLDER_ID}' in parents "
      f"and mimeType='application/vnd.google-apps.document' "
      f"and trashed=false",
    fields="files(id, name)"
).execute()

google_docs = results.get("files", [])


# ============================================================
# MAKE SURE GOOGLE SHEET HAS ALL DOCUMENTS
# ============================================================

existing_rows = sheet.get_all_records()

existing_ids = {
    str(row["document_id"])
    for row in existing_rows
    if row.get("document_id")
}


for file in google_docs:

    if file["id"] not in existing_ids:

        sheet.append_row([
            file["id"],
            file["name"],
            "FALSE"
        ])


# ============================================================
# READ SHARED SELECTION
# ============================================================

shared_rows = sheet.get_all_records()

shared_selection = {
    str(row["document_id"]):
        str(row["selected"]).upper() == "TRUE"
    for row in shared_rows
}


# ============================================================
# READ SHARED ORDER
# ============================================================

shared_order = [
    str(row["document_id"])
    for row in shared_rows
    if row.get("document_id")
]


# ============================================================
# TABS
# ============================================================

tab1, tab2 = st.tabs([
    "📁 Select documents",
    "👀 Preview"
])


# ============================================================
# TAB 1
# ============================================================

with tab1:

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
        # CURRENT SHARED SELECTION
        # ----------------------------------------------------

        current_selection = []

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
        # UPDATE SHARED SELECTION
        # ----------------------------------------------------

        st.divider()

        if st.button(
            "💾 Update shared selection",
            type="primary",
            use_container_width=True
        ):

            for file in google_docs:

                selected = (
                    file["id"]
                    in current_selection
                )

                # Find document row
                cell = sheet.find(
                    file["id"]
                )

                sheet.update_cell(
                    cell.row,
                    3,
                    "TRUE"
                    if selected
                    else "FALSE"
                )

            st.success(
                "Shared selection updated! ✅"
            )

            st.rerun()


        # ----------------------------------------------------
        # SELECTED DOCUMENTS
        # ----------------------------------------------------

        selected_files = [
            file
            for file in google_docs
            if file["id"]
            in current_selection
        ]


        if selected_files:

            st.divider()

            st.subheader(
                "Document order"
            )

            st.write(
                "Drag the documents to "
                "change their order."
            )


            # ------------------------------------------------
            # INITIAL ORDER
            # ------------------------------------------------

            selected_ids = [
                file["id"]
                for file in selected_files
            ]


            # Keep existing shared order
            # where possible

            ordered_ids = [
                doc_id
                for doc_id in shared_order
                if doc_id in selected_ids
            ]


            # Add newly selected documents
            # at the end

            for doc_id in selected_ids:

                if doc_id not in ordered_ids:

                    ordered_ids.append(
                        doc_id
                    )


            id_to_name = {
                file["id"]: file["name"]
                for file in selected_files
            }


            ordered_names = [
                id_to_name[doc_id]
                for doc_id in ordered_ids
            ]


            # ------------------------------------------------
            # DRAG & DROP
            # ------------------------------------------------

            new_order_names = sort_items(
                ordered_names
            )


            # Convert names back to IDs

            name_to_id = {
                file["name"]: file["id"]
                for file in selected_files
            }


            new_order_ids = [
                name_to_id[name]
                for name in new_order_names
            ]


            # ------------------------------------------------
            # SAVE ORDER
            # ------------------------------------------------

            if st.button(
                "💾 Save document order",
                use_container_width=True
            ):

                # Read all rows again
                rows = sheet.get_all_records()

                # Create mapping
                row_by_id = {
                    str(row["document_id"]):
                        index + 2
                    for index, row
                    in enumerate(rows)
                }


                # We use column 4 for order
                #
                # If your sheet currently only has
                # 3 columns, this will create column D.

                for position, doc_id in enumerate(
                    new_order_ids,
                    start=1
                ):

                    row_number = row_by_id.get(
                        doc_id
                    )

                    if row_number:

                        sheet.update_cell(
                            row_number,
                            4,
                            position
                        )


                st.success(
                    "Document order saved! ✅"
                )

                st.rerun()


            # ------------------------------------------------
            # SHOW ORDER
            # ------------------------------------------------

            st.write(
                "### Current order"
            )

            for i, name in enumerate(
                new_order_names,
                start=1
            ):

                st.write(
                    f"**{i}.** 📄 {name}"
                )


# ============================================================
# TAB 2 — PREVIEW
# ============================================================

with tab2:

    st.header(
        "👀 Combined document"
    )


    # --------------------------------------------------------
    # GET CURRENT SHARED DATA AGAIN
    # --------------------------------------------------------

    shared_rows = sheet.get_all_records()


    shared_selection = {
        str(row["document_id"]):
            str(row["selected"]).upper() == "TRUE"
        for row in shared_rows
    }


    shared_order_data = []

    for row in shared_rows:

        if row.get("selected"):

            try:

                order = int(
                    row.get(
                        "order",
                        999999
                    )
                )

            except:

                order = 999999


            shared_order_data.append(
                (
                    order,
                    str(row["document_id"])
                )
            )


    # Sort by order

    shared_order_data.sort(
        key=lambda x: x[0]
    )


    selected_ids = [
        doc_id
        for _, doc_id
        in shared_order_data
        if shared_selection.get(
            doc_id,
            False
        )
    ]


    # --------------------------------------------------------
    # GET FILES
    # --------------------------------------------------------

    selected_files = [
        file
        for file in google_docs
        if file["id"] in selected_ids
    ]


    # If there is no saved order yet,
    # use Drive order.

    if not selected_files:

        st.info(
            "No documents have been selected yet."
        )

    else:

        st.write(
            f"**{len(selected_files)} documents** "
            "in the shared compilation."
        )


        # ----------------------------------------------------
        # CREATE COMBINED PDF
        # ----------------------------------------------------

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
        # WRITE PDF
        # ----------------------------------------------------

        combined_pdf = BytesIO()

        pdf_writer.write(
            combined_pdf
        )

        combined_pdf.seek(0)

        pdf_bytes = (
            combined_pdf.getvalue()
        )


        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        st.download_button(
            label="⬇️ Download combined PDF",
            data=pdf_bytes,
            file_name="KerkSlides_Compiled.pdf",
            mime="application/pdf",
            use_container_width=True
        )


        st.divider()


        # ====================================================
        # PDF VIEWER
        # ====================================================

        st.subheader(
            "📖 Document preview"
        )


        # ----------------------------------------------------
        # BASE64
        # ----------------------------------------------------

        pdf_base64 = base64.b64encode(
            pdf_bytes
        ).decode(
            "utf-8"
        )


        # ----------------------------------------------------
        # CUSTOM PDF VIEWER
        # ----------------------------------------------------

        viewer_html = f"""

<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<script src="
https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js
">
</script>


<style>

* {{
    box-sizing: border-box;
}}


body {{
    margin: 0;
    padding: 0;
    font-family: Arial, sans-serif;
}}


#viewer {{
    width: 100%;
    height: 900px;
    background: #525659;

    display: flex;
    flex-direction: column;

    overflow: hidden;
}}


#toolbar {{

    height: 55px;
    min-height: 55px;

    background: #2f3133;

    display: flex;

    align-items: center;

    justify-content: center;

    gap: 8px;

    padding: 8px;

    z-index: 10;
}}


button {{

    background: white;

    border: none;

    border-radius: 6px;

    padding: 8px 13px;

    font-size: 15px;

    cursor: pointer;
}}


button:hover {{
    background: #eeeeee;
}}


#page-info {{

    color: white;

    margin: 0 10px;

    font-size: 14px;
}}


#pdf-container {{

    flex: 1;

    overflow-y: auto;

    overflow-x: auto;

    padding: 25px;

    text-align: center;
}}


.page {{

    display: block;

    margin: 0 auto 25px auto;

    box-shadow:
        0 2px 10px
        rgba(0,0,0,0.4);

    background: white;
}}


</style>

</head>


<body>


<div id="viewer">


    <div id="toolbar">


        <button onclick="zoomOut()">
            −
        </button>


        <button onclick="zoomIn()">
            +
        </button>


        <button onclick="resetZoom()">
            Reset
        </button>


        <span id="page-info">
            Loading...
        </span>


        <button onclick="goFullscreen()">
            ⛶ Full screen
        </button>


    </div>


    <div id="pdf-container">

        <div
            style="
                color:white;
                font-size:18px;
                padding-top:40px;
            "
        >
            Loading document...
        </div>

    </div>


</div>


<script>


const pdfData =
    atob("{pdf_base64}");


let pdfDoc = null;

let scale = 1.2;

let rendering = false;


/* =========================================================
   LOAD PDF
========================================================= */


async function loadPDF() {{

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

}}


/* =========================================================
   RENDER
========================================================= */


async function renderAllPages() {{

    if (rendering) {{
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


/* =========================================================
   ZOOM IN
========================================================= */


function zoomIn() {{

    scale += 0.2;

    renderAllPages();

}}


/* =========================================================
   ZOOM OUT
========================================================= */


function zoomOut() {{

    if (scale > 0.4) {{

        scale -= 0.2;

        renderAllPages();

    }}

}}


/* =========================================================
   RESET
========================================================= */


function resetZoom() {{

    scale = 1.2;

    renderAllPages();

}}


/* =========================================================
   FULLSCREEN
========================================================= */


function goFullscreen() {{

    const viewer =
        document.getElementById(
            "viewer"
        );


    if (
        document.fullscreenElement
    ) {{

        document.exitFullscreen();

    }}

    else {{

        if (
            viewer.requestFullscreen
        ) {{

            viewer.requestFullscreen();

        }}

        else if (
            viewer.webkitRequestFullscreen
        ) {{

            viewer.webkitRequestFullscreen();

        }}

    }}

}}


/* =========================================================
   START
========================================================= */


loadPDF();


</script>


</body>

</html>

"""


        st.components.v1.html(
            viewer_html,
            height=920,
            scrolling=False
        )

