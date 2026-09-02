import base64
from io import BytesIO

import gspread
import streamlit as st
import streamlit.components.v1 as components
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pypdf import PdfReader, PdfWriter

SOURCE_FOLDER_ID = "1q-5HeICSq5zBoQAEDb_PNA3iMXbgrNBn"
SPREADSHEET_ID = "1f4EFf5HeWCUtPtqYtsoooOAXpibKiuXEoWU0CHAOjWQ"
OUTPUT_FILE_NAME = "KerkSlides_Compiled.pdf"
REQUIRED_HEADERS = ["document_id", "document_name", "selected"]

presentation_mode = st.query_params.get("view", "") == "presentation"

st.set_page_config(
    page_title="KerkSlides Presentation" if presentation_mode else "KerkSlides",
    page_icon="⛪",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if presentation_mode:
    st.markdown(
        """
        <style>
        #MainMenu, header, footer,
        [data-testid="stToolbar"], [data-testid="stDecoration"],
        [data-testid="stStatusWidget"], [data-testid="stSidebar"],
        [data-testid="collapsedControl"] { display:none !important; }
        html, body, .stApp { background:#202124; overflow:hidden; }
        .block-container { max-width:100% !important; padding:0 !important; margin:0 !important; }
        iframe { display:block; border:0; }
        </style>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        """
        <style>
        .block-container { max-width:1200px; padding-top:1.5rem; padding-bottom:3rem; }
        [data-testid="stHeader"] { background:transparent; }
        </style>
        """,
        unsafe_allow_html=True,
    )

try:
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ],
    )
    drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    sheet = gspread.authorize(credentials).open_by_key(SPREADSHEET_ID).sheet1
except Exception as error:
    st.error("Could not connect to Google Drive or Google Sheets.")
    st.exception(error)
    st.stop()


def ensure_headers():
    if sheet.row_values(1) != REQUIRED_HEADERS:
        sheet.update(range_name="A1:C1", values=[REQUIRED_HEADERS], value_input_option="RAW")


try:
    ensure_headers()
except Exception as error:
    st.error("Could not prepare the Google Sheet.")
    st.exception(error)
    st.stop()


@st.cache_data(show_spinner=False, ttl=60)
def get_google_docs():
    files = []
    page_token = None
    while True:
        result = drive_service.files().list(
            q=(
                f"'{SOURCE_FOLDER_ID}' in parents and "
                "mimeType='application/vnd.google-apps.document' and trashed=false"
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


def get_shared_selection():
    selection = {}
    for row in sheet.get_all_records():
        document_id = str(row.get("document_id", "")).strip()
        selected = str(row.get("selected", "")).strip().upper() in {"TRUE", "1", "YES"}
        if document_id:
            selection[document_id] = selected
    return selection


def save_shared_selection(google_docs, selected_ids):
    selected_ids = set(map(str, selected_ids))
    rows = [REQUIRED_HEADERS]
    for file in google_docs:
        document_id = str(file["id"])
        rows.append([
            document_id,
            str(file["name"]),
            "TRUE" if document_id in selected_ids else "FALSE",
        ])

    if sheet.row_count < len(rows):
        sheet.add_rows(len(rows) - sheet.row_count)
    sheet.batch_clear([f"A1:C{sheet.row_count}"])
    sheet.update(
        range_name=f"A1:C{len(rows)}",
        values=rows,
        value_input_option="RAW",
    )


def get_selected_files(google_docs, selection):
    return [file for file in google_docs if selection.get(str(file["id"]), False)]


def compile_selected_pdf(selected_files):
    if not selected_files:
        return None
    writer = PdfWriter()
    for file in selected_files:
        pdf_data = drive_service.files().export_media(
            fileId=file["id"],
            mimeType="application/pdf",
        ).execute()
        reader = PdfReader(BytesIO(pdf_data))
        for page in reader.pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@st.cache_data(show_spinner=False, ttl=300)
def compile_pdf_cached(document_ids, modified_times):
    del modified_times
    lookup = {str(file["id"]): file for file in google_docs}
    selected_files = [lookup[document_id] for document_id in document_ids if document_id in lookup]
    return compile_selected_pdf(selected_files)


def create_pdf_viewer(pdf_bytes):
    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
    return f"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<style>
* {{ box-sizing:border-box; }}
html, body {{ width:100%; height:100%; margin:0; overflow:hidden; background:#202124; font-family:Arial,sans-serif; }}
#viewer {{ position:fixed; inset:0; display:flex; flex-direction:column; background:#202124; }}
#toolbar {{ min-height:54px; display:flex; align-items:center; justify-content:center; gap:7px; padding:7px; background:#292b2d; z-index:2; }}
button {{ min-width:42px; min-height:38px; border:0; border-radius:8px; padding:8px 11px; cursor:pointer; font-weight:700; }}
button:disabled {{ opacity:.4; cursor:default; }}
#page-info {{ min-width:80px; color:white; text-align:center; }}
#stage {{ flex:1; min-height:0; overflow:auto; display:flex; align-items:center; justify-content:center; padding:8px; background:#525659; }}
canvas {{ display:none; background:white; box-shadow:0 3px 14px rgba(0,0,0,.45); }}
#message {{ color:white; text-align:center; padding:24px; }}
#error {{ display:none; color:white; background:#b3261e; padding:14px; border-radius:8px; }}
@media(max-width:600px) {{ #toolbar {{ gap:4px; }} button {{ min-width:36px; padding:7px 8px; }} #page-info {{ min-width:58px; font-size:12px; }} }}
</style>
</head>
<body>
<div id="viewer">
  <div id="toolbar">
    <button id="previous">◀</button><span id="page-info">Loading...</span><button id="next">▶</button>
    <button id="zoom-out">−</button><button id="fit">Fit</button><button id="zoom-in">+</button>
    <button id="fullscreen">⛶</button>
  </div>
  <div id="stage"><div id="message">Loading presentation...</div><div id="error">The presentation could not be loaded.</div><canvas id="canvas"></canvas></div>
</div>
<script>
pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
const raw = atob("{pdf_base64}");
const pdfData = new Uint8Array(raw.length);
for (let i = 0; i < raw.length; i++) pdfData[i] = raw.charCodeAt(i);

const viewer = document.getElementById("viewer");
const stage = document.getElementById("stage");
const canvas = document.getElementById("canvas");
const context = canvas.getContext("2d");
const pageInfo = document.getElementById("page-info");
const previousButton = document.getElementById("previous");
const nextButton = document.getElementById("next");
const message = document.getElementById("message");
const errorBox = document.getElementById("error");
let pdfDocument = null;
let currentPage = 1;
let fitScale = 1;
let zoomFactor = 1;
let renderTask = null;
let renderVersion = 0;

async function calculateFit(page) {{
  const viewport = page.getViewport({{scale:1}});
  return Math.min(
    Math.max(stage.clientWidth - 16, 100) / viewport.width,
    Math.max(stage.clientHeight - 16, 100) / viewport.height
  );
}}

async function renderPage(recalculateFit=false) {{
  if (!pdfDocument) return;
  const version = ++renderVersion;
  if (renderTask) {{ try {{ renderTask.cancel(); }} catch (_) {{}} }}
  try {{
    const page = await pdfDocument.getPage(currentPage);
    if (version !== renderVersion) return;
    if (recalculateFit) fitScale = await calculateFit(page);
    const viewport = page.getViewport({{scale:fitScale * zoomFactor}});
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.floor(viewport.width * ratio);
    canvas.height = Math.floor(viewport.height * ratio);
    canvas.style.width = Math.floor(viewport.width) + "px";
    canvas.style.height = Math.floor(viewport.height) + "px";
    renderTask = page.render({{
      canvasContext:context,
      viewport:viewport,
      transform:ratio === 1 ? null : [ratio,0,0,ratio,0,0]
    }});
    await renderTask.promise;
    if (version !== renderVersion) return;
    canvas.style.display = "block";
    message.style.display = "none";
    errorBox.style.display = "none";
    pageInfo.textContent = `${{currentPage}} / ${{pdfDocument.numPages}}`;
    previousButton.disabled = currentPage <= 1;
    nextButton.disabled = currentPage >= pdfDocument.numPages;
    stage.scrollTop = 0;
    stage.scrollLeft = 0;
  }} catch (error) {{
    if (error && error.name === "RenderingCancelledException") return;
    console.error(error);
    message.style.display = "none";
    errorBox.style.display = "block";
    pageInfo.textContent = "Error";
  }} finally {{ renderTask = null; }}
}}

function go(delta) {{
  if (!pdfDocument) return;
  const target = Math.min(Math.max(currentPage + delta, 1), pdfDocument.numPages);
  if (target !== currentPage) {{ currentPage = target; renderPage(false); }}
}}
previousButton.onclick = () => go(-1);
nextButton.onclick = () => go(1);
document.getElementById("zoom-in").onclick = () => {{ zoomFactor = Math.min(zoomFactor + .2, 3); renderPage(false); }};
document.getElementById("zoom-out").onclick = () => {{ zoomFactor = Math.max(zoomFactor - .2, .4); renderPage(false); }};
document.getElementById("fit").onclick = () => {{ zoomFactor = 1; renderPage(true); }};
document.getElementById("fullscreen").onclick = async () => {{
  try {{
    if (document.fullscreenElement) await document.exitFullscreen();
    else await viewer.requestFullscreen();
  }} catch (error) {{ console.error(error); }}
}};
document.addEventListener("keydown", event => {{
  if (["ArrowRight", "PageDown", " "].includes(event.key)) {{ event.preventDefault(); go(1); }}
  if (["ArrowLeft", "PageUp"].includes(event.key)) {{ event.preventDefault(); go(-1); }}
}});
let touchStartX = null;
stage.addEventListener("touchstart", event => {{ if (event.touches.length === 1) touchStartX = event.touches[0].clientX; }}, {{passive:true}});
stage.addEventListener("touchend", event => {{
  if (touchStartX === null || event.changedTouches.length !== 1) return;
  const distance = event.changedTouches[0].clientX - touchStartX;
  if (Math.abs(distance) > 70) go(distance < 0 ? 1 : -1);
  touchStartX = null;
}}, {{passive:true}});
let resizeTimer;
window.addEventListener("resize", () => {{
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {{ zoomFactor = 1; renderPage(true); }}, 200);
}});
document.addEventListener("fullscreenchange", () => setTimeout(() => {{ zoomFactor = 1; renderPage(true); }}, 150));
(async () => {{
  try {{
    pdfDocument = await pdfjsLib.getDocument({{data:pdfData}}).promise;
    await renderPage(true);
  }} catch (error) {{
    console.error(error);
    message.style.display = "none";
    errorBox.style.display = "block";
    pageInfo.textContent = "Error";
  }}
}})();
</script>
</body>
</html>
"""


try:
    google_docs = get_google_docs()
except Exception as error:
    st.error("Could not load the Google Docs.")
    st.exception(error)
    st.stop()

if presentation_mode:
    try:
        selection = get_shared_selection()
        selected_files = get_selected_files(google_docs, selection)
    except Exception as error:
        st.error("Could not load the shared selection.")
        st.exception(error)
        st.stop()

    if not selected_files:
        st.markdown(
            """
            <div style="color:white;padding:60px 20px;text-align:center;font-family:Arial,sans-serif">
              <h2>No documents selected</h2>
              <p>Return to KerkSlides and save a selection first.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.stop()

    try:
        with st.spinner("Creating presentation..."):
            pdf_bytes = compile_selected_pdf(selected_files)
    except Exception as error:
        st.error("Could not compile the presentation.")
        st.exception(error)
        st.stop()

    components.html(create_pdf_viewer(pdf_bytes), height=900, scrolling=False)
    st.stop()

st.title("⛪ KerkSlides")
st.caption("Select Google Docs, create one combined PDF, and open it as a presentation.")

header_left, header_right = st.columns([5, 1])
with header_right:
    if st.button("🔄 Refresh", use_container_width=True):
        get_google_docs.clear()
        st.cache_data.clear()
        st.rerun()

tab_select, tab_preview = st.tabs(["📁 Select documents", "👀 Preview"])

with tab_select:
    st.header("Select documents")
    if not google_docs:
        st.warning("No Google Docs were found in the source folder.")
    else:
        try:
            shared_selection = get_shared_selection()
        except Exception as error:
            st.error("Could not read the current selection.")
            st.exception(error)
            st.stop()

        st.write(f"Found **{len(google_docs)} documents**.")
        current_selection = []
        for file in google_docs:
            document_id = str(file["id"])
            if st.checkbox(
                file["name"],
                value=shared_selection.get(document_id, False),
                key=f"checkbox_{document_id}",
            ):
                current_selection.append(document_id)

        st.divider()
        if st.button("💾 Update shared selection", type="primary", use_container_width=True):
            try:
                save_shared_selection(google_docs, current_selection)
                st.cache_data.clear()
                st.success("Shared selection updated.")
                st.rerun()
            except Exception as error:
                st.error("Could not update the shared selection.")
                st.exception(error)

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
        st.info("No documents are selected. Select documents in the first tab and save the selection.")
    else:
        st.write(f"**{len(selected_files)} documents** selected.")
        with st.expander("View selected documents"):
            for index, file in enumerate(selected_files, start=1):
                st.write(f"{index}. {file['name']}")

        document_ids = tuple(str(file["id"]) for file in selected_files)
        modified_times = tuple(str(file.get("modifiedTime", "")) for file in selected_files)
        try:
            with st.spinner("Creating combined document..."):
                pdf_bytes = compile_pdf_cached(document_ids, modified_times)
        except Exception as error:
            st.error("Could not export and combine the selected documents.")
            st.exception(error)
            st.stop()

        combined_reader = PdfReader(BytesIO(pdf_bytes))
        st.write(f"Combined PDF pages: **{len(combined_reader.pages)}**")
        st.download_button(
            "⬇️ Download combined PDF",
            data=pdf_bytes,
            file_name=OUTPUT_FILE_NAME,
            mime="application/pdf",
            use_container_width=True,
        )

        # Working presentation button. It opens this same app with
        # ?view=presentation in a new browser tab.
        st.markdown(
            """
            <a href="?view=presentation" target="_blank" rel="noopener noreferrer"
               style="display:flex;width:100%;min-height:42px;padding:.65rem 1rem;
                      border-radius:8px;background:#ff4b4b;color:white;
                      align-items:center;justify-content:center;text-align:center;
                      text-decoration:none;font-weight:600;box-sizing:border-box;">
                🎥 Open standalone presentation
            </a>
            """,
            unsafe_allow_html=True,
        )
        st.caption("The presentation uses the last selection saved to Google Sheets.")

        st.divider()
        st.subheader("📖 Document preview")
        components.html(create_pdf_viewer(pdf_bytes), height=800, scrolling=False)
