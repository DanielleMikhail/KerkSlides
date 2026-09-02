import base64
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

import gspread
import streamlit as st
import streamlit.components.v1 as components
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pypdf import PdfReader, PdfWriter

try:
    from streamlit_sortables import sort_items
    from streamlit_searchbox import st_searchbox
except ImportError:
    st.error(
        "Add streamlit-sortables==0.3.1 and "
        "streamlit-searchbox==0.1.24 to requirements.txt."
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

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
WORD_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
SUPPORTED_MIME_TYPES = {GOOGLE_DOC_MIME, WORD_DOCX_MIME}


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
            div.stButton > button[kind="primary"] {
                background: var(--ks-green);
                border-color: var(--ks-green);
            }
            div.stButton > button[kind="primary"]:hover {
                background: var(--ks-green-dark);
                border-color: var(--ks-green-dark);
            }
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
            "https://www.googleapis.com/auth/drive.readonly",
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

@st.cache_data(show_spinner=False, ttl=30)
def get_supported_documents():
    """Load native Google Docs and uploaded Microsoft Word DOCX files."""
    files = []
    page_token = None

    mime_query = (
        f"mimeType='{GOOGLE_DOC_MIME}' or mimeType='{WORD_DOCX_MIME}'"
    )

    while True:
        result = drive_service.files().list(
            q=(
                f"'{SOURCE_FOLDER_ID}' in parents and "
                f"({mime_query}) and trashed=false"
            ),
            fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
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
    selected_rows = []
    for row_index, row in enumerate(sheet.get_all_records()):
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


def save_shared_selection(documents, ordered_ids):
    ordered_ids = [str(document_id) for document_id in ordered_ids]
    order_lookup = {
        document_id: position
        for position, document_id in enumerate(ordered_ids, start=1)
    }

    values = [["document_id", "document_name", "selected", "sort_order"]]
    for file in documents:
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


def get_selected_files(documents, ordered_ids):
    file_by_id = {str(file["id"]): file for file in documents}
    return [file_by_id[doc_id] for doc_id in ordered_ids if doc_id in file_by_id]


def download_drive_file(document_id):
    """Download a regular Drive file, such as an uploaded DOCX."""
    buffer = BytesIO()
    request = drive_service.files().get_media(
        fileId=document_id,
        supportsAllDrives=True,
    )
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def convert_docx_to_pdf(docx_bytes, original_name):
    """Convert DOCX bytes to PDF using LibreOffice in headless mode."""
    with tempfile.TemporaryDirectory() as temp_directory:
        temp_path = Path(temp_directory)
        safe_name = Path(original_name).name
        if not safe_name.lower().endswith(".docx"):
            safe_name += ".docx"

        docx_path = temp_path / safe_name
        docx_path.write_bytes(docx_bytes)

        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(temp_path),
                str(docx_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        pdf_path = temp_path / f"{docx_path.stem}.pdf"
        if result.returncode != 0 or not pdf_path.exists():
            details = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                "Microsoft Word conversion failed. Make sure LibreOffice is "
                f"installed. Details: {details or 'No PDF was created.'}"
            )

        return pdf_path.read_bytes()


def document_to_pdf(file):
    """Return PDF bytes for either a Google Doc or a Word DOCX file."""
    mime_type = file.get("mimeType")

    if mime_type == GOOGLE_DOC_MIME:
        return drive_service.files().export_media(
            fileId=file["id"],
            mimeType="application/pdf",
        ).execute()

    if mime_type == WORD_DOCX_MIME:
        docx_bytes = download_drive_file(file["id"])
        return convert_docx_to_pdf(docx_bytes, file["name"])

    raise ValueError(f"Unsupported document type: {mime_type}")


def compile_selected_pdf(selected_files):
    if not selected_files:
        return None

    writer = PdfWriter()
    for file in selected_files:
        pdf_bytes = document_to_pdf(file)
        reader = PdfReader(BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)

    combined_pdf = BytesIO()
    writer.write(combined_pdf)
    return combined_pdf.getvalue()


@st.cache_data(show_spinner=False, ttl=300)
def compile_pdf_cached(document_ids, modified_times):
    # modified_times is intentionally part of the cache key. If a document is
    # edited, Streamlit creates a new cached compiled PDF.
    del modified_times
    file_by_id = {str(file["id"]): file for file in documents}
    selected_files = [
        file_by_id[document_id]
        for document_id in document_ids
        if document_id in file_by_id
    ]
    return compile_selected_pdf(selected_files)


# ============================================================
# PDF VIEWER
# ============================================================

def create_scrollable_pdf_viewer(pdf_bytes):
    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>
* {{ box-sizing: border-box; }}
html, body {{ width:100%; height:100%; margin:0; overflow:hidden; background:#202124; }}
iframe {{ width:100%; height:100%; border:0; display:block; }}
</style>
</head>
<body>
<iframe src="data:application/pdf;base64,{pdf_base64}#toolbar=1&navpanes=0&view=FitH"></iframe>
</body>
</html>
"""


# ============================================================
# INITIALIZE DATA
# ============================================================

try:
    ensure_sheet_headers()
    documents = get_supported_documents()
except Exception as error:
    st.error("Could not load the documents or prepare the Google Sheet.")
    st.exception(error)
    st.stop()


# ============================================================
# PRESENTATION MODE
# ============================================================

if presentation_mode:
    try:
        ordered_ids = get_shared_selection()
        selected_files = get_selected_files(documents, ordered_ids)
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

file_by_id = {str(file["id"]): file for file in documents}
all_ids = list(file_by_id)

if "ordered_song_ids" not in st.session_state:
    st.session_state.ordered_song_ids = [
        doc_id for doc_id in get_shared_selection() if doc_id in file_by_id
    ]
else:
    # Remove IDs for files that no longer exist or are no longer supported.
    st.session_state.ordered_song_ids = [
        doc_id
        for doc_id in st.session_state.ordered_song_ids
        if doc_id in file_by_id
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
    if st.button("🔄 Refresh document library", use_container_width=True):
        get_supported_documents.clear()
        st.rerun()

    st.caption(
        "Loads Google Docs and Microsoft Word .docx files. "
        "Use Refresh after uploading a new file."
    )


# ============================================================
# HOME
# ============================================================

if active_page == "🏠 Home":
    st.markdown('<div class="ks-kicker">Church presentation manager</div>', unsafe_allow_html=True)
    st.markdown('<div class="ks-title">KerkSlides Dashboard</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ks-subtitle">Choose documents, arrange the service order and open one continuous presentation.</div>',
        unsafe_allow_html=True,
    )

    saved_ids = get_shared_selection()
    google_doc_count = sum(file.get("mimeType") == GOOGLE_DOC_MIME for file in documents)
    word_count = sum(file.get("mimeType") == WORD_DOCX_MIME for file in documents)

    card1, card2, card3 = st.columns(3)
    with card1:
        st.markdown(
            f'<div class="ks-card"><div class="ks-card-label">Document library</div>'
            f'<div class="ks-card-value">{len(documents)}</div>'
            f'<div class="ks-card-note">{google_doc_count} Google Docs, {word_count} Word files</div></div>',
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
        '<div class="ks-subtitle">Search Google Docs and Word files, add them, then drag them into order.</div>',
        unsafe_allow_html=True,
    )

    def display_name(doc_id):
        file = file_by_id[doc_id]
        suffix = "Word" if file.get("mimeType") == WORD_DOCX_MIME else "Google Doc"
        return f"{file['name']}  ·  {suffix}"

    def search_songs(search_term):
        term = search_term.strip().casefold()
        matching_ids = all_ids if not term else [
            doc_id
            for doc_id in all_ids
            if term in file_by_id[doc_id]["name"].casefold()
        ]
        return [(display_name(doc_id), doc_id) for doc_id in matching_ids[:30]]

    search_col, add_col = st.columns([5, 1], vertical_alignment="bottom")
    with search_col:
        song_to_add = st_searchbox(
            search_songs,
            key="song_autocomplete",
            label="Search document library",
            placeholder="Type a few letters of a song title...",
            default_options=[
                (display_name(doc_id), doc_id) for doc_id in all_ids[:20]
            ],
            clear_on_submit=False,
            edit_after_submit="current",
            debounce=150,
        )

    with add_col:
        add_clicked = st.button(
            "＋ Add",
            type="primary",
            use_container_width=True,
            disabled=song_to_add is None,
        )

    if add_clicked and song_to_add:
        if song_to_add not in st.session_state.ordered_song_ids:
            st.session_state.ordered_song_ids.append(song_to_add)
            st.success(f"Added: {file_by_id[song_to_add]['name']}")
        else:
            st.info("That song is already in the service order.")

    st.markdown("### Selected songs")
    st.caption("Drag a song card up or down to change the presentation order.")

    if not st.session_state.ordered_song_ids:
        st.info("No songs selected yet. Search for a song above and click Add.")
    else:
        name_counts = {}
        for doc_id in st.session_state.ordered_song_ids:
            name = file_by_id[doc_id]["name"]
            name_counts[name] = name_counts.get(name, 0) + 1

        label_to_id = {}
        sortable_labels = []
        for doc_id in st.session_state.ordered_song_ids:
            file = file_by_id[doc_id]
            name = file["name"]
            file_type = "Word" if file.get("mimeType") == WORD_DOCX_MIME else "Google Doc"
            label = f"{name} · {file_type}"
            if name_counts[name] > 1:
                label += f" ({doc_id[-5:]})"
            label_to_id[label] = doc_id
            sortable_labels.append(label)

        sorted_labels = sort_items(
            sortable_labels,
            direction="vertical",
            custom_style="""
            .sortable-component {
                display:flex; flex-direction:column; gap:10px;
                padding:4px; background:transparent;
            }
            .sortable-item {
                padding:14px 16px; border:1px solid #e5e7eb;
                border-radius:14px; background:#ffffff; color:#202124;
                box-shadow:0 3px 12px rgba(17,24,39,.05);
                font-size:15px; font-weight:650; cursor:grab;
            }
            .sortable-item:before { content:"☰  "; color:#6b7280; }
            """,
            key="service_order_sortable",
        )

        st.session_state.ordered_song_ids = [
            label_to_id[label] for label in sorted_labels
        ]

        remove_song = st.selectbox(
            "Remove a selected song",
            options=st.session_state.ordered_song_ids,
            index=None,
            format_func=display_name,
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
            save_shared_selection(documents, st.session_state.ordered_song_ids)
            compile_pdf_cached.clear()
            st.success("The service order has been saved.")
        except Exception as error:
            st.error("Could not save the service order.")
            st.exception(error)


# ============================================================
# PRESENTATION ACTIONS
# ============================================================

if active_page == "🎥 Presentation":
    st.markdown('<div class="ks-kicker">Ready to present</div>', unsafe_allow_html=True)
    st.markdown('<div class="ks-title">Presentation</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ks-subtitle">Open presentation mode or download the combined PDF.</div>',
        unsafe_allow_html=True,
    )

    try:
        saved_ids = get_shared_selection()
        selected_files = get_selected_files(documents, saved_ids)
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
            st.error("Could not export and combine the selected documents.")
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
