import base64
from io import BytesIO

import gspread
import streamlit as st
import streamlit.components.v1 as components
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pypdf import PdfReader, PdfWriter


# ============================================================
# APP MODE AND PAGE SETUP
# ============================================================

presentation_mode = st.query_params.get("view", "") == "presentation"

st.set_page_config(
    page_title="KerkSlides Presentation" if presentation_mode else "KerkSlides",
    page_icon="⛪",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# CONFIGURATION
# ============================================================

SOURCE_FOLDER_ID = "1q-5HeICSq5zBoQAEDb_PNA3iMXbgrNBn"
SPREADSHEET_ID = "1f4EFf5HeWCUtPtqYtsoooOAXpibKiuXEoWU0CHAOjWQ"
OUTPUT_FILE_NAME = "KerkSlides_Compiled.pdf"


# ============================================================
# STYLING
# ============================================================

if presentation_mode:
    st.markdown(
        """
        <style>
            #MainMenu, header, footer,
            [data-testid="stToolbar"],
            [data-testid="stDecoration"],
            [data-testid="stStatusWidget"],
            [data-testid="stSidebar"],
            [data-testid="collapsedControl"] {
                display: none !important;
            }
            html, body, .stApp {
                background: #202124;
                overflow: hidden;
            }
            .block-container {
                max-width: 100% !important;
                padding: 0 !important;
                margin: 0 !important;
            }
            iframe { display: block; border: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        """
        <style>
            :root {
                --ks-green: #39c86a;
                --ks-green-dark: #279b4e;
                --ks-ink: #202124;
                --ks-muted: #6b7280;
                --ks-card: #ffffff;
                --ks-bg: #f3f4f6;
                --ks-border: #e5e7eb;
            }
            .stApp { background: var(--ks-bg); }
            .block-container {
                max-width: 1180px;
                padding-top: 1.4rem;
                padding-bottom: 4rem;
            }
            h1, h2, h3 { color: var(--ks-ink); letter-spacing: -0.02em; }
            .ks-kicker {
                color: var(--ks-muted);
                font-size: .85rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: .08em;
                margin-bottom: .25rem;
            }
            .ks-title {
                color: var(--ks-ink);
                font-size: clamp(1.8rem, 5vw, 2.8rem);
                font-weight: 800;
                line-height: 1.05;
                margin-bottom: .3rem;
            }
            .ks-subtitle { color: var(--ks-muted); margin-bottom: 1.3rem; }
            .ks-card {
                background: white;
                border: 1px solid var(--ks-border);
                border-radius: 18px;
                padding: 18px;
                min-height: 132px;
                box-shadow: 0 5px 18px rgba(17, 24, 39, .05);
            }
            .ks-card-label {
                color: var(--ks-muted);
                font-size: .78rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: .05em;
            }
            .ks-card-value {
                color: var(--ks-ink);
                font-size: 1.55rem;
                font-weight: 800;
                margin-top: .35rem;
            }
            .ks-card-note { color: var(--ks-muted); font-size: .85rem; margin-top: .3rem; }
            .ks-order-number {
                width: 32px;
                height: 32px;
                border-radius: 10px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: #e9f9ef;
                color: var(--ks-green-dark);
                font-weight: 800;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] {
                border-color: var(--ks-border);
                border-radius: 16px;
                background: white;
                box-shadow: 0 3px 14px rgba(17, 24, 39, .035);
            }
            div.stButton > button[kind="primary"] {
                background: var(--ks-green);
                border-color: var(--ks-green);
            }
            div.stButton > button[kind="primary"]:hover {
                background: var(--ks-green-dark);
                border-color: var(--ks-green-dark);
            }
            /* Fixed mobile-style bottom navigation */
            .st-key-fixed_bottom_nav {
                position: fixed;
                left: 0;
                right: 0;
                bottom: 0;
                z-index: 9999;
                display: flex;
                justify-content: center;
                padding: 8px max(12px, env(safe-area-inset-right))
                         calc(8px + env(safe-area-inset-bottom))
                         max(12px, env(safe-area-inset-left));
                background: rgba(255, 255, 255, 0.96);
                border-top: 1px solid var(--ks-border);
                box-shadow: 0 -8px 24px rgba(17, 24, 39, .10);
                backdrop-filter: blur(14px);
                -webkit-backdrop-filter: blur(14px);
                width: 100vw !important;
                visibility: visible !important;
            }
            .st-key-fixed_bottom_nav > div {
                width: min(520px, 100%);
            }
            .st-key-fixed_bottom_nav [data-testid="stRadio"] > label {
                display: none;
            }
            .st-key-fixed_bottom_nav [role="radiogroup"] {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 8px;
                width: 100%;
            }
            .st-key-fixed_bottom_nav [role="radio"] {
                min-height: 48px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 13px;
                color: var(--ks-muted);
                font-weight: 700;
                cursor: pointer;
            }
            .st-key-fixed_bottom_nav [role="radio"][aria-checked="true"] {
                color: var(--ks-green-dark);
                background: #e9f9ef;
            }
            .st-key-fixed_bottom_nav [data-baseweb="radio"] > div:first-child {
                display: none;
            }
            .block-container {
                padding-bottom: 7.5rem;
            }
            @media (max-width: 640px) {
                .block-container { padding: 1rem .8rem 3rem; }
                .ks-card { min-height: 112px; padding: 15px; }
                .ks-card-value { font-size: 1.25rem; }
                h2 { font-size: 1.35rem; }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
        "drive", "v3", credentials=credentials, cache_discovery=False
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
    expected = ["document_id", "document_name", "selected", "sort_order"]
    if sheet.row_values(1) != expected:
        sheet.update(
            range_name="A1:D1",
            values=[expected],
            value_input_option="RAW",
        )


def get_shared_selection():
    """Return selected document IDs in their saved presentation order."""
    rows = sheet.get_all_records()
    selected_rows = []
    for row_index, row in enumerate(rows):
        document_id = str(row.get("document_id", "")).strip()
        selected = str(row.get("selected", "")).strip().upper() in {
            "TRUE", "1", "YES"
        }
        if not document_id or not selected:
            continue
        try:
            order = int(row.get("sort_order") or row_index + 1)
        except (TypeError, ValueError):
            order = row_index + 1
        selected_rows.append((order, row_index, document_id))
    selected_rows.sort(key=lambda item: (item[0], item[1]))
    return [document_id for _, _, document_id in selected_rows]


def save_shared_selection(google_docs, ordered_ids):
    ordered_ids = [str(document_id) for document_id in ordered_ids]
    order_lookup = {
        document_id: position
        for position, document_id in enumerate(ordered_ids, start=1)
    }
    values = [["document_id", "document_name", "selected", "sort_order"]]
    for file in google_docs:
        document_id = str(file["id"])
        values.append([
            document_id,
            str(file["name"]),
            "TRUE" if document_id in order_lookup else "FALSE",
            order_lookup.get(document_id, ""),
        ])
    required_rows = max(len(values), 2)
    if sheet.row_count < required_rows:
        sheet.add_rows(required_rows - sheet.row_count)
    sheet.batch_clear([f"A1:D{sheet.row_count}"])
    sheet.update(
        range_name=f"A1:D{len(values)}",
        values=values,
        value_input_option="RAW",
    )


def get_selected_files(google_docs, ordered_ids):
    file_by_id = {str(file["id"]): file for file in google_docs}
    return [file_by_id[doc_id] for doc_id in ordered_ids if doc_id in file_by_id]


def export_google_doc_as_pdf(document_id):
    return drive_service.files().export_media(
        fileId=document_id, mimeType="application/pdf"
    ).execute()


def compile_selected_pdf(selected_files):
    if not selected_files:
        return None
    writer = PdfWriter()
    for file in selected_files:
        reader = PdfReader(BytesIO(export_google_doc_as_pdf(file["id"])))
        for page in reader.pages:
            writer.add_page(page)
    combined_pdf = BytesIO()
    writer.write(combined_pdf)
    return combined_pdf.getvalue()


@st.cache_data(show_spinner=False, ttl=300)
def compile_pdf_cached(document_ids, modified_times):
    del modified_times
    file_by_id = {str(file["id"]): file for file in google_docs}
    selected_files = [
        file_by_id[document_id]
        for document_id in document_ids
        if document_id in file_by_id
    ]
    return compile_selected_pdf(selected_files)


# ============================================================
# PDF.JS VIEWER
# ============================================================

def create_scrollable_pdf_viewer(pdf_bytes):
    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<style>
* {{ box-sizing: border-box; }}
html, body {{ width:100%; height:100%; margin:0; overflow:hidden; background:#202124; font-family:Arial,sans-serif; }}
#viewer {{ position:fixed; inset:0; display:flex; flex-direction:column; }}
#toolbar {{ flex:0 0 auto; min-height:52px; display:flex; align-items:center; justify-content:center; gap:8px; padding:7px; background:#292b2d; color:white; z-index:10; }}
#page-status {{ min-width:100px; text-align:center; font-size:13px; font-weight:700; }}
button {{ min-width:40px; min-height:36px; border:0; border-radius:9px; padding:7px 10px; background:white; color:#202124; font-weight:700; cursor:pointer; }}
#scroll-container {{ flex:1 1 auto; min-height:0; overflow:auto; -webkit-overflow-scrolling:touch; scroll-behavior:smooth; padding:12px 8px 24px; background:#525659; }}
#pages {{ display:flex; flex-direction:column; align-items:center; gap:12px; min-width:100%; }}
.pdf-page {{ display:block; background:white; box-shadow:0 3px 14px rgba(0,0,0,.45); }}
#loading {{ padding:45px 20px; color:white; text-align:center; }}
#error {{ display:none; max-width:560px; margin:30px auto; padding:15px; border-radius:8px; background:#b3261e; color:white; text-align:center; }}
@media(max-width:600px) {{ #toolbar{{gap:4px}} button{{font-size:12px;padding:6px 8px}} #page-status{{min-width:75px;font-size:11px}} }}
</style>
</head>
<body>
<div id="viewer">
  <div id="toolbar">
    <button id="zoom-out">−</button>
    <button id="fit-width">Fit</button>
    <button id="zoom-in">+</button>
    <span id="page-status">Loading...</span>
    <button id="fullscreen">⛶</button>
  </div>
  <div id="scroll-container">
    <div id="loading">Loading presentation...</div>
    <div id="error">The presentation could not be loaded.</div>
    <div id="pages"></div>
  </div>
</div>
<script>
pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
const rawPdf = window.atob("{pdf_base64}");
const pdfData = new Uint8Array(rawPdf.length);
for (let i=0; i<rawPdf.length; i++) pdfData[i] = rawPdf.charCodeAt(i);
const viewer=document.getElementById("viewer"), scrollContainer=document.getElementById("scroll-container"), pagesElement=document.getElementById("pages"), loadingElement=document.getElementById("loading"), errorElement=document.getElementById("error"), pageStatus=document.getElementById("page-status");
let pdfDocument=null, zoomFactor=1, fitWidthScale=1, renderVersion=0, resizeTimer=null;
function availablePageWidth() {{ return Math.max(scrollContainer.clientWidth-22,120); }}
async function calculateFitWidth() {{ const page=await pdfDocument.getPage(1); return availablePageWidth()/page.getViewport({{scale:1}}).width; }}
async function renderAllPages(recalculateFit=false) {{
  if(!pdfDocument) return;
  const currentVersion=++renderVersion;
  if(recalculateFit) fitWidthScale=await calculateFitWidth();
  pagesElement.innerHTML=""; loadingElement.style.display="block"; errorElement.style.display="none";
  const scale=fitWidthScale*zoomFactor, outputScale=window.devicePixelRatio||1;
  try {{
    for(let pageNumber=1; pageNumber<=pdfDocument.numPages; pageNumber++) {{
      if(currentVersion!==renderVersion) return;
      pageStatus.textContent=`${{pageNumber}} / ${{pdfDocument.numPages}}`;
      const page=await pdfDocument.getPage(pageNumber), viewport=page.getViewport({{scale}}), canvas=document.createElement("canvas"), context=canvas.getContext("2d");
      canvas.className="pdf-page"; canvas.width=Math.floor(viewport.width*outputScale); canvas.height=Math.floor(viewport.height*outputScale); canvas.style.width=Math.floor(viewport.width)+"px"; canvas.style.height=Math.floor(viewport.height)+"px"; pagesElement.appendChild(canvas);
      await page.render({{canvasContext:context, viewport, transform:outputScale===1?null:[outputScale,0,0,outputScale,0,0]}}).promise;
    }}
    if(currentVersion===renderVersion) {{ loadingElement.style.display="none"; pageStatus.textContent=`${{pdfDocument.numPages}} pages`; }}
  }} catch(error) {{ console.error(error); loadingElement.style.display="none"; errorElement.style.display="block"; pageStatus.textContent="Error"; }}
}}
document.getElementById("zoom-in").onclick=()=>{{zoomFactor=Math.min(zoomFactor+.15,2.5);renderAllPages(false)}};
document.getElementById("zoom-out").onclick=()=>{{zoomFactor=Math.max(zoomFactor-.15,.4);renderAllPages(false)}};
document.getElementById("fit-width").onclick=()=>{{zoomFactor=1;renderAllPages(true)}};
document.getElementById("fullscreen").onclick=async()=>{{if(document.fullscreenElement)await document.exitFullscreen();else if(viewer.requestFullscreen)await viewer.requestFullscreen();else if(viewer.webkitRequestFullscreen)viewer.webkitRequestFullscreen();}};
window.addEventListener("resize",()=>{{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{{zoomFactor=1;renderAllPages(true)}},250)}});
(async()=>{{try{{pdfDocument=await pdfjsLib.getDocument({{data:pdfData}}).promise;await renderAllPages(true)}}catch(error){{console.error(error);loadingElement.style.display="none";errorElement.style.display="block";pageStatus.textContent="Error"}}}})();
</script>
</body>
</html>
"""


# ============================================================
# ORDERING HELPERS
# ============================================================

def reconcile_order(previous_order, chosen_ids):
    chosen_set = set(chosen_ids)
    retained = [doc_id for doc_id in previous_order if doc_id in chosen_set]
    added = [doc_id for doc_id in chosen_ids if doc_id not in retained]
    return retained + added


def move_item(items, index, direction):
    target = index + direction
    if 0 <= target < len(items):
        items[index], items[target] = items[target], items[index]


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
        ordered_ids = get_shared_selection()
        selected_files = get_selected_files(google_docs, ordered_ids)
    except Exception as error:
        st.error("Could not load the shared selection.")
        st.exception(error)
        st.stop()

    if not selected_files:
        st.markdown(
            '<div style="color:white;padding:60px 20px;text-align:center;font-family:Arial">'
            '<h2>No songs selected</h2><p>Return to KerkSlides and save a song order first.</p></div>',
            unsafe_allow_html=True,
        )
        st.stop()

    try:
        document_ids = tuple(str(file["id"]) for file in selected_files)
        modified_times = tuple(str(file.get("modifiedTime", "")) for file in selected_files)
        with st.spinner("Creating presentation..."):
            pdf_bytes = compile_pdf_cached(document_ids, modified_times)
    except Exception as error:
        st.error("Could not compile the presentation.")
        st.exception(error)
        st.stop()

    components.html(create_scrollable_pdf_viewer(pdf_bytes), height=900, scrolling=False)
    st.stop()


# ============================================================
# DASHBOARD HEADER AND STATE
# ============================================================

file_by_id = {str(file["id"]): file for file in google_docs}
all_ids = list(file_by_id)

if "ordered_song_ids" not in st.session_state:
    st.session_state.ordered_song_ids = [
        doc_id for doc_id in get_shared_selection() if doc_id in file_by_id
    ]

st.markdown('<div class="ks-kicker">Church presentation manager</div>', unsafe_allow_html=True)
st.markdown('<div class="ks-title">KerkSlides Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="ks-subtitle">Choose songs, arrange the service order and open one continuous presentation.</div>', unsafe_allow_html=True)

card1, card2, card3 = st.columns(3)
with card1:
    st.markdown(
        f'<div class="ks-card"><div class="ks-card-label">Song library</div><div class="ks-card-value">{len(google_docs)}</div><div class="ks-card-note">Google Docs available</div></div>',
        unsafe_allow_html=True,
    )
with card2:
    st.markdown(
        f'<div class="ks-card"><div class="ks-card-label">Current service</div><div class="ks-card-value">{len(st.session_state.ordered_song_ids)} songs</div><div class="ks-card-note">Saved order can be updated below</div></div>',
        unsafe_allow_html=True,
    )
with card3:
    st.markdown(
        '<div class="ks-card"><div class="ks-card-label">Presentation</div><div class="ks-card-value">Ready</div><div class="ks-card-note">Scrollable and fullscreen</div></div>',
        unsafe_allow_html=True,
    )

st.write("")

# The keyed container is fixed to the viewport bottom by CSS.
# Using a container is more reliable across Streamlit versions than
# targeting the generated class of the radio widget itself.
with st.container(key="fixed_bottom_nav"):
    active_page = st.radio(
        "Navigation",
        options=["🎵 Songs", "🎥 Presentation"],
        horizontal=True,
        label_visibility="collapsed",
        key="bottom_navigation_choice",
    )


# ============================================================
# SONG SELECTION AND ORDER
# ============================================================

if active_page == "🎵 Songs":
    toolbar_left, toolbar_right = st.columns([5, 1])
    with toolbar_left:
        st.subheader("Build the song list")
        st.caption("Click the field and start typing to search the song library.")
    with toolbar_right:
        if st.button("↻ Refresh", use_container_width=True):
            get_google_docs.clear()
            st.cache_data.clear()
            st.rerun()

    chosen_ids = st.multiselect(
        "Search and select songs",
        options=all_ids,
        default=[doc_id for doc_id in st.session_state.ordered_song_ids if doc_id in file_by_id],
        format_func=lambda doc_id: file_by_id[doc_id]["name"],
        placeholder="Type a song title...",
        key="song_picker",
    )

    st.session_state.ordered_song_ids = reconcile_order(
        st.session_state.ordered_song_ids, chosen_ids
    )

    if not st.session_state.ordered_song_ids:
        st.info("No songs selected yet. Search for one or more song titles above.")
    else:
        st.markdown("### Service order")
        st.caption("Use the arrows to determine the exact order in the compiled PDF.")

        for index, document_id in enumerate(st.session_state.ordered_song_ids):
            with st.container(border=True):
                number_col, title_col, up_col, down_col, remove_col = st.columns(
                    [0.55, 6, 0.75, 0.75, 0.85], vertical_alignment="center"
                )
                with number_col:
                    st.markdown(f'<span class="ks-order-number">{index + 1}</span>', unsafe_allow_html=True)
                with title_col:
                    st.markdown(f"**{file_by_id[document_id]['name']}**")
                with up_col:
                    if st.button("↑", key=f"up_{document_id}", disabled=index == 0, help="Move up", use_container_width=True):
                        move_item(st.session_state.ordered_song_ids, index, -1)
                        st.rerun()
                with down_col:
                    if st.button("↓", key=f"down_{document_id}", disabled=index == len(st.session_state.ordered_song_ids) - 1, help="Move down", use_container_width=True):
                        move_item(st.session_state.ordered_song_ids, index, 1)
                        st.rerun()
                with remove_col:
                    if st.button("✕", key=f"remove_{document_id}", help="Remove", use_container_width=True):
                        st.session_state.ordered_song_ids.remove(document_id)
                        del st.session_state["song_picker"]
                        st.rerun()

    st.write("")
    save_col, clear_col = st.columns([3, 1])
    with save_col:
        if st.button("💾 Save service order", type="primary", use_container_width=True):
            try:
                save_shared_selection(google_docs, st.session_state.ordered_song_ids)
                st.cache_data.clear()
                st.success("The shared song selection and presentation order were saved.")
            except Exception as error:
                st.error("Could not save the service order.")
                st.exception(error)
    with clear_col:
        if st.button("Clear", use_container_width=True):
            st.session_state.ordered_song_ids = []
            if "song_picker" in st.session_state:
                del st.session_state["song_picker"]
            st.rerun()


# ============================================================
# PRESENTATION PREVIEW
# ============================================================

if active_page == "🎥 Presentation":
    st.subheader("Presentation")
    st.caption("This preview uses the last service order saved to Google Sheets.")

    try:
        saved_ids = get_shared_selection()
        selected_files = get_selected_files(google_docs, saved_ids)
    except Exception as error:
        st.error("Could not read the saved service order.")
        st.exception(error)
        st.stop()

    if not selected_files:
        st.info("Select songs in the Songs tab and save the service order first.")
    else:
        with st.container(border=True):
            st.markdown(f"**{len(selected_files)} songs in the presentation**")
            for index, file in enumerate(selected_files, start=1):
                st.caption(f"{index}. {file['name']}")

        try:
            document_ids = tuple(str(file["id"]) for file in selected_files)
            modified_times = tuple(str(file.get("modifiedTime", "")) for file in selected_files)
            with st.spinner("Creating the combined presentation..."):
                pdf_bytes = compile_pdf_cached(document_ids, modified_times)
        except Exception as error:
            st.error("Could not export and combine the selected songs.")
            st.exception(error)
            st.stop()

        action1, action2 = st.columns(2)
        with action1:
            st.download_button(
                "⬇ Download combined PDF",
                data=pdf_bytes,
                file_name=OUTPUT_FILE_NAME,
                mime="application/pdf",
                use_container_width=True,
            )
        with action2:
            st.link_button(
                "🎥 Open presentation",
                "?view=presentation",
                type="primary",
                use_container_width=True,
            )

        combined_reader = PdfReader(BytesIO(pdf_bytes))
        st.caption(f"{len(combined_reader.pages)} total PDF pages")
        components.html(create_scrollable_pdf_viewer(pdf_bytes), height=760, scrolling=False)
