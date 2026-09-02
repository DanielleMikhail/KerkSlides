import base64
from io import BytesIO

import gspread
import streamlit as st
import streamlit.components.v1 as components
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pypdf import PdfReader, PdfWriter

try:
    from streamlit_sortables import sort_items
except ImportError:
    st.error(
        "The package 'streamlit-sortables' is missing. Add "
        "streamlit-sortables==0.3.1 to requirements.txt."
    )
    st.stop()


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
                font-size: .82rem;
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
            .ks-card-note {
                color: var(--ks-muted);
                font-size: .85rem;
                margin-top: .3rem;
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

            /* Collapsible side panel */
            [data-testid="stSidebar"] {
                background: rgba(255, 255, 255, .98);
                border-right: 1px solid var(--ks-border);
                box-shadow: 8px 0 24px rgba(17, 24, 39, .06);
            }
            [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
                padding-top: 1rem;
            }
            .ks-sidebar-brand { padding: .35rem .25rem 1rem; }
            .ks-sidebar-title {
                color: var(--ks-ink);
                font-size: 1.35rem;
                font-weight: 800;
            }
            .ks-sidebar-note {
                color: var(--ks-muted);
                font-size: .82rem;
                margin-top: .25rem;
            }
            [data-testid="stSidebar"] [data-testid="stRadio"] > label {
                display: none;
            }
            [data-testid="stSidebar"] [role="radiogroup"] {
                display: flex;
                flex-direction: column;
                gap: 8px;
                width: 100%;
            }
            [data-testid="stSidebar"] [role="radio"] {
                min-height: 50px;
                display: flex;
                align-items: center;
                padding: 0 14px;
                border-radius: 13px;
                color: var(--ks-muted);
                font-weight: 700;
                cursor: pointer;
            }
            [data-testid="stSidebar"] [role="radio"][aria-checked="true"] {
                color: var(--ks-green-dark);
                background: #e9f9ef;
            }
            [data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child {
                display: none;
            }
            [data-testid="collapsedControl"] {
                background: white;
                border: 1px solid var(--ks-border);
                border-radius: 0 12px 12px 0;
                box-shadow: 3px 3px 12px rgba(17, 24, 39, .10);
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
        fileId=document_id,
        mimeType="application/pdf",
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
* {{ box-sizing:border-box; }}
html,body {{ width:100%;height:100%;margin:0;overflow:hidden;background:#202124;font-family:Arial,sans-serif; }}
#viewer {{ position:fixed;inset:0;display:flex;flex-direction:column; }}
#toolbar {{ flex:0 0 auto;min-height:52px;display:flex;align-items:center;justify-content:center;gap:8px;padding:7px;background:#292b2d;color:white;z-index:10; }}
#page-status {{ min-width:100px;text-align:center;font-size:13px;font-weight:700; }}
button {{ min-width:40px;min-height:36px;border:0;border-radius:9px;padding:7px 10px;background:white;color:#202124;font-weight:700;cursor:pointer; }}
#scroll-container {{ flex:1 1 auto;min-height:0;overflow:auto;-webkit-overflow-scrolling:touch;scroll-behavior:smooth;padding:12px 8px 24px;background:#525659; }}
#pages {{ display:flex;flex-direction:column;align-items:center;gap:12px;min-width:100%; }}
.pdf-page {{ display:block;background:white;box-shadow:0 3px 14px rgba(0,0,0,.45); }}
#loading {{ padding:45px 20px;color:white;text-align:center; }}
#error {{ display:none;max-width:560px;margin:30px auto;padding:15px;border-radius:8px;background:#b3261e;color:white;text-align:center; }}
</style>
</head>
<body>
<div id="viewer">
  <div id="toolbar">
    <button id="zoom-out">−</button><button id="fit-width">Fit</button>
    <button id="zoom-in">+</button><span id="page-status">Loading...</span>
    <button id="fullscreen">⛶</button>
  </div>
  <div id="scroll-container">
    <div id="loading">Loading presentation...</div>
    <div id="error">The presentation could not be loaded.</div>
    <div id="pages"></div>
  </div>
</div>
<script>
pdfjsLib.GlobalWorkerOptions.workerSrc="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
const rawPdf=window.atob("{pdf_base64}");
const pdfData=new Uint8Array(rawPdf.length);
for(let i=0;i<rawPdf.length;i++) pdfData[i]=rawPdf.charCodeAt(i);
const viewer=document.getElementById("viewer"),scrollContainer=document.getElementById("scroll-container"),pagesElement=document.getElementById("pages"),loadingElement=document.getElementById("loading"),errorElement=document.getElementById("error"),pageStatus=document.getElementById("page-status");
let pdfDocument=null,zoomFactor=1,fitWidthScale=1,renderVersion=0,resizeTimer=null;
function availablePageWidth(){{return Math.max(scrollContainer.clientWidth-22,120);}}
async function calculateFitWidth(){{const page=await pdfDocument.getPage(1);return availablePageWidth()/page.getViewport({{scale:1}}).width;}}
async function renderAllPages(recalculateFit=false){{
 if(!pdfDocument)return;const currentVersion=++renderVersion;
 if(recalculateFit)fitWidthScale=await calculateFitWidth();
 pagesElement.innerHTML="";loadingElement.style.display="block";errorElement.style.display="none";
 const scale=fitWidthScale*zoomFactor,outputScale=window.devicePixelRatio||1;
 try{{for(let pageNumber=1;pageNumber<=pdfDocument.numPages;pageNumber++){{
  if(currentVersion!==renderVersion)return;pageStatus.textContent=`${{pageNumber}} / ${{pdfDocument.numPages}}`;
  const page=await pdfDocument.getPage(pageNumber),viewport=page.getViewport({{scale}}),canvas=document.createElement("canvas"),context=canvas.getContext("2d");
  canvas.className="pdf-page";canvas.width=Math.floor(viewport.width*outputScale);canvas.height=Math.floor(viewport.height*outputScale);canvas.style.width=Math.floor(viewport.width)+"px";canvas.style.height=Math.floor(viewport.height)+"px";pagesElement.appendChild(canvas);
  await page.render({{canvasContext:context,viewport,transform:outputScale===1?null:[outputScale,0,0,outputScale,0,0]}}).promise;
 }}if(currentVersion===renderVersion){{loadingElement.style.display="none";pageStatus.textContent=`${{pdfDocument.numPages}} pages`;}}
 }}catch(error){{console.error(error);loadingElement.style.display="none";errorElement.style.display="block";pageStatus.textContent="Error";}}
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
            '<h2>No songs selected</h2><p>Return to KerkSlides and save a service order first.</p></div>',
            unsafe_allow_html=True,
        )
        st.stop()

    document_ids = tuple(str(file["id"]) for file in selected_files)
    modified_times = tuple(str(file.get("modifiedTime", "")) for file in selected_files)
    try:
        with st.spinner("Creating presentation..."):
            pdf_bytes = compile_pdf_cached(document_ids, modified_times)
    except Exception as error:
        st.error("Could not compile the presentation.")
        st.exception(error)
        st.stop()

    components.html(create_scrollable_pdf_viewer(pdf_bytes), height=900, scrolling=False)
    st.stop()


# ============================================================
# APP STATE AND SIDEBAR
# ============================================================

file_by_id = {str(file["id"]): file for file in google_docs}
all_ids = list(file_by_id)

if "ordered_song_ids" not in st.session_state:
    st.session_state.ordered_song_ids = [
        doc_id for doc_id in get_shared_selection() if doc_id in file_by_id
    ]

with st.sidebar:
    st.markdown(
        """
        <div class="ks-sidebar-brand">
            <div class="ks-sidebar-title">⛪ KerkSlides</div>
            <div class="ks-sidebar-note">Service presentation manager</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    active_page = st.radio(
        "Navigation",
        options=["🏠 Home", "🎵 Songs", "🎥 Presentation"],
        label_visibility="collapsed",
        key="side_navigation",
    )
    st.divider()
    st.caption("Use the arrow to hide the panel. Use the sidebar control to open it again.")


# ============================================================
# HOME
# ============================================================

if active_page == "🏠 Home":
    st.markdown('<div class="ks-kicker">Church presentation manager</div>', unsafe_allow_html=True)
    st.markdown('<div class="ks-title">KerkSlides Dashboard</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ks-subtitle">Choose songs, arrange the service order and open one continuous presentation.</div>',
        unsafe_allow_html=True,
    )

    saved_ids = get_shared_selection()
    card1, card2, card3 = st.columns(3)
    with card1:
        st.markdown(
            f'<div class="ks-card"><div class="ks-card-label">Song library</div>'
            f'<div class="ks-card-value">{len(google_docs)}</div>'
            '<div class="ks-card-note">Google Docs available</div></div>',
            unsafe_allow_html=True,
        )
    with card2:
        st.markdown(
            f'<div class="ks-card"><div class="ks-card-label">Current service</div>'
            f'<div class="ks-card-value">{len(saved_ids)} songs</div>'
            '<div class="ks-card-note">Saved presentation order</div></div>',
            unsafe_allow_html=True,
        )
    with card3:
        status = "Ready" if saved_ids else "Not ready"
        note = "Presentation can be opened" if saved_ids else "Add and save songs first"
        st.markdown(
            f'<div class="ks-card"><div class="ks-card-label">Presentation</div>'
            f'<div class="ks-card-value">{status}</div>'
            f'<div class="ks-card-note">{note}</div></div>',
            unsafe_allow_html=True,
        )


# ============================================================
# SONGS
# ============================================================

if active_page == "🎵 Songs":
    st.markdown('<div class="ks-kicker">Service builder</div>', unsafe_allow_html=True)
    st.markdown('<div class="ks-title">Songs</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ks-subtitle">Search for a song, add it, then drag the songs into the required order.</div>',
        unsafe_allow_html=True,
    )

    # Use a real text input so tapping the search field always opens the
    # on-screen keyboard on iPhone and Android. A selectbox is a combobox and
    # some mobile browsers do not focus its internal search input reliably.
    search_col, add_col = st.columns([5, 1], vertical_alignment="bottom")
    with search_col:
        search_query = st.text_input(
            "Search song library",
            placeholder="Type a song title...",
            key="song_search_query",
            autocomplete="off",
        )

    normalized_query = search_query.strip().casefold()
    matching_ids = [
        doc_id
        for doc_id in all_ids
        if normalized_query in file_by_id[doc_id]["name"].casefold()
    ] if normalized_query else []

    # Keep the chosen result in session state while the user adds songs.
    if matching_ids:
        if st.session_state.get("song_result_choice") not in matching_ids:
            st.session_state.song_result_choice = matching_ids[0]
        song_to_add = st.selectbox(
            "Matching songs",
            options=matching_ids[:25],
            format_func=lambda doc_id: file_by_id[doc_id]["name"],
            key="song_result_choice",
            help="Choose the song to add when several titles match.",
        )
    else:
        song_to_add = None

    with add_col:
        add_clicked = st.button(
            "＋ Add",
            type="primary",
            use_container_width=True,
            disabled=song_to_add is None,
        )

    if normalized_query and not matching_ids:
        st.caption("No songs match this search.")

    if add_clicked and song_to_add:
        if song_to_add not in st.session_state.ordered_song_ids:
            st.session_state.ordered_song_ids.append(song_to_add)
            st.success(f"Added: {file_by_id[song_to_add]['name']}")
        else:
            st.info("That song is already in the service order.")

    st.markdown("### Selected songs")
    st.caption("Drag a song card up or down. The search result remains available after adding.")

    if not st.session_state.ordered_song_ids:
        st.info("No songs selected yet. Search for a song above and click Add.")
    else:
        # Make labels unique without exposing IDs unless duplicate names exist.
        name_counts = {}
        for doc_id in st.session_state.ordered_song_ids:
            name = file_by_id[doc_id]["name"]
            name_counts[name] = name_counts.get(name, 0) + 1

        label_to_id = {}
        sortable_labels = []
        for doc_id in st.session_state.ordered_song_ids:
            name = file_by_id[doc_id]["name"]
            label = name if name_counts[name] == 1 else f"{name} ({doc_id[-5:]})"
            label_to_id[label] = doc_id
            sortable_labels.append(label)

        sortable_style = """
        .sortable-component {
            display: flex;
            flex-direction: column;
            gap: 10px;
            padding: 4px;
            background: transparent;
        }
        .sortable-item {
            padding: 14px 16px;
            border: 1px solid #e5e7eb;
            border-radius: 14px;
            background: #ffffff;
            color: #202124;
            box-shadow: 0 3px 12px rgba(17, 24, 39, .05);
            font-size: 15px;
            font-weight: 650;
            cursor: grab;
        }
        .sortable-item:before {
            content: "☰  ";
            color: #6b7280;
        }
        """

        sorted_labels = sort_items(
            sortable_labels,
            direction="vertical",
            custom_style=sortable_style,
            key="service_order_sortable",
        )
        new_order = [label_to_id[label] for label in sorted_labels]
        if new_order != st.session_state.ordered_song_ids:
            st.session_state.ordered_song_ids = new_order

        remove_song = st.selectbox(
            "Remove a selected song",
            options=st.session_state.ordered_song_ids,
            index=None,
            format_func=lambda doc_id: file_by_id[doc_id]["name"],
            placeholder="Choose a song to remove...",
            key="remove_song_choice",
        )
        if st.button("Remove selected song", disabled=remove_song is None):
            st.session_state.ordered_song_ids.remove(remove_song)
            st.rerun()

    st.write("")
    if st.button(
        "💾 Save service order",
        type="primary",
        use_container_width=True,
        disabled=not st.session_state.ordered_song_ids,
    ):
        try:
            save_shared_selection(google_docs, st.session_state.ordered_song_ids)
            st.cache_data.clear()
            st.success("The service order has been saved.")
        except Exception as error:
            st.error("Could not save the service order.")
            st.exception(error)


# ============================================================
# PRESENTATION ACTIONS ONLY
# ============================================================

if active_page == "🎥 Presentation":
    st.markdown('<div class="ks-kicker">Ready to present</div>', unsafe_allow_html=True)
    st.markdown('<div class="ks-title">Presentation</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ks-subtitle">Open the presentation in presentation mode or download the compiled PDF.</div>',
        unsafe_allow_html=True,
    )

    try:
        saved_ids = get_shared_selection()
        selected_files = get_selected_files(google_docs, saved_ids)
    except Exception as error:
        st.error("Could not read the saved service order.")
        st.exception(error)
        st.stop()

    if not selected_files:
        st.info("Add songs on the Songs page and save the service order first.")
    else:
        document_ids = tuple(str(file["id"]) for file in selected_files)
        modified_times = tuple(str(file.get("modifiedTime", "")) for file in selected_files)
        try:
            with st.spinner("Creating the presentation..."):
                pdf_bytes = compile_pdf_cached(document_ids, modified_times)
        except Exception as error:
            st.error("Could not export and combine the selected songs.")
            st.exception(error)
            st.stop()

        action1, action2 = st.columns(2)
        with action1:
            st.link_button(
                "🎥 Open presentation",
                "?view=presentation",
                type="primary",
                use_container_width=True,
            )
        with action2:
            st.download_button(
                "⬇ Download combined PDF",
                data=pdf_bytes,
                file_name=OUTPUT_FILE_NAME,
                mime="application/pdf",
                use_container_width=True,
            )
