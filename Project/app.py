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
    st.error("Add streamlit-sortables==0.3.1 to requirements.txt.")
    st.stop()

presentation_mode = st.query_params.get("view", "") == "presentation"
st.set_page_config(
    page_title="KerkSlides Presentation" if presentation_mode else "KerkSlides",
    page_icon="⛪",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SOURCE_FOLDER_ID = "1q-5HeICSq5zBoQAEDb_PNA3iMXbgrNBn"
SPREADSHEET_ID = "1f4EFf5HeWCUtPtqYtsoooOAXpibKiuXEoWU0CHAOjWQ"
OUTPUT_FILE_NAME = "KerkSlides_Compiled.pdf"

st.markdown("""
<style>
:root{--green:#39c86a;--dark:#279b4e;--ink:#202124;--muted:#6b7280;--bg:#f3f4f6;--border:#e5e7eb}
.stApp{background:var(--bg)}
.block-container{max-width:1180px;padding-top:1.4rem;padding-bottom:4rem}
.ks-kicker{color:var(--muted);font-size:.82rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em}
.ks-title{color:var(--ink);font-size:clamp(1.8rem,5vw,2.8rem);font-weight:800;line-height:1.05;margin:.25rem 0}
.ks-subtitle{color:var(--muted);margin-bottom:1.3rem}
.ks-card{background:#fff;border:1px solid var(--border);border-radius:18px;padding:18px;min-height:125px;box-shadow:0 5px 18px rgba(17,24,39,.05)}
.ks-label{color:var(--muted);font-size:.78rem;font-weight:700;text-transform:uppercase}.ks-value{font-size:1.5rem;font-weight:800;margin-top:.4rem}.ks-note{color:var(--muted);font-size:.85rem}
div.stButton>button[kind="primary"]{background:var(--green);border-color:var(--green)}
.st-key-song_search_query input{min-height:54px;border-radius:14px;font-size:16px;background:white}
.st-key-song_result_choice [data-baseweb="select"]>div{min-height:54px;border-radius:14px;background:white}
[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--border)}
[data-testid="stSidebar"] [data-testid="stRadio"]>label{display:none}
[data-testid="stSidebar"] [role="radiogroup"]{display:flex;flex-direction:column;gap:8px}
[data-testid="stSidebar"] [role="radio"]{min-height:50px;display:flex;align-items:center;padding:0 14px;border-radius:13px;color:var(--muted);font-weight:700}
[data-testid="stSidebar"] [role="radio"][aria-checked="true"]{color:var(--dark);background:#e9f9ef}
[data-testid="stSidebar"] [data-baseweb="radio"]>div:first-child{display:none}
@media(max-width:640px){.block-container{padding:1rem .8rem 3rem}.ks-card{min-height:105px;padding:14px}}
</style>
""", unsafe_allow_html=True)

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

@st.cache_data(show_spinner=False, ttl=60)
def get_google_docs():
    files, token = [], None
    while True:
        result = drive_service.files().list(
            q=f"'{SOURCE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.document' and trashed=false",
            fields="nextPageToken, files(id, name, modifiedTime)",
            orderBy="name", pageToken=token, pageSize=1000,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        files.extend(result.get("files", []))
        token = result.get("nextPageToken")
        if not token:
            return files

def ensure_sheet_headers():
    headers = ["document_id", "document_name", "selected", "sort_order"]
    if sheet.row_values(1) != headers:
        sheet.update(range_name="A1:D1", values=[headers], value_input_option="RAW")

def get_shared_selection():
    selected = []
    for i, row in enumerate(sheet.get_all_records()):
        doc_id = str(row.get("document_id", "")).strip()
        is_selected = str(row.get("selected", "")).strip().upper() in {"TRUE", "1", "YES"}
        if doc_id and is_selected:
            try:
                order = int(row.get("sort_order") or i + 1)
            except (TypeError, ValueError):
                order = i + 1
            selected.append((order, i, doc_id))
    selected.sort()
    return [doc_id for _, _, doc_id in selected]

def save_shared_selection(files, ordered_ids):
    order = {doc_id: i for i, doc_id in enumerate(ordered_ids, 1)}
    values = [["document_id", "document_name", "selected", "sort_order"]]
    for file in files:
        doc_id = str(file["id"])
        values.append([doc_id, file["name"], "TRUE" if doc_id in order else "FALSE", order.get(doc_id, "")])
    if sheet.row_count < len(values):
        sheet.add_rows(len(values) - sheet.row_count)
    sheet.batch_clear([f"A1:D{sheet.row_count}"])
    sheet.update(range_name=f"A1:D{len(values)}", values=values, value_input_option="RAW")

def get_selected_files(files, ordered_ids):
    lookup = {str(file["id"]): file for file in files}
    return [lookup[doc_id] for doc_id in ordered_ids if doc_id in lookup]

def compile_pdf(files):
    writer = PdfWriter()
    for file in files:
        data = drive_service.files().export_media(fileId=file["id"], mimeType="application/pdf").execute()
        for page in PdfReader(BytesIO(data)).pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()

@st.cache_data(show_spinner=False, ttl=300)
def compile_pdf_cached(document_ids, modified_times):
    del modified_times
    lookup = {str(file["id"]): file for file in google_docs}
    return compile_pdf([lookup[doc_id] for doc_id in document_ids if doc_id in lookup])

def show_pdf(pdf_bytes, height=900):
    encoded = base64.b64encode(pdf_bytes).decode("ascii")
    html = f"""
    <html><body style='margin:0;background:#202124'>
    <iframe src='data:application/pdf;base64,{encoded}#toolbar=1&navpanes=0&view=FitH'
      style='position:fixed;inset:0;width:100%;height:100%;border:0'></iframe>
    </body></html>
    """
    components.html(html, height=height, scrolling=False)

try:
    ensure_sheet_headers()
    google_docs = get_google_docs()
except Exception as error:
    st.error("Could not load the Google Docs or prepare the Google Sheet.")
    st.exception(error)
    st.stop()

if presentation_mode:
    selected_files = get_selected_files(google_docs, get_shared_selection())
    if not selected_files:
        st.error("No songs have been saved yet.")
        st.stop()
    ids = tuple(str(file["id"]) for file in selected_files)
    times = tuple(str(file.get("modifiedTime", "")) for file in selected_files)
    with st.spinner("Creating presentation..."):
        show_pdf(compile_pdf_cached(ids, times))
    st.stop()

file_by_id = {str(file["id"]): file for file in google_docs}
all_ids = list(file_by_id)
if "ordered_song_ids" not in st.session_state:
    st.session_state.ordered_song_ids = [doc_id for doc_id in get_shared_selection() if doc_id in file_by_id]

with st.sidebar:
    st.markdown("## ⛪ KerkSlides")
    st.caption("Service presentation manager")
    active_page = st.radio("Navigation", ["🏠 Home", "🎵 Songs", "🎥 Presentation"], label_visibility="collapsed")

if active_page == "🏠 Home":
    st.markdown('<div class="ks-kicker">Church presentation manager</div><div class="ks-title">KerkSlides Dashboard</div><div class="ks-subtitle">Choose songs, arrange the order and open one continuous presentation.</div>', unsafe_allow_html=True)
    saved = get_shared_selection()
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f'<div class="ks-card"><div class="ks-label">Song library</div><div class="ks-value">{len(google_docs)}</div><div class="ks-note">Google Docs available</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="ks-card"><div class="ks-label">Current service</div><div class="ks-value">{len(saved)} songs</div><div class="ks-note">Saved order</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="ks-card"><div class="ks-label">Presentation</div><div class="ks-value">{"Ready" if saved else "Not ready"}</div><div class="ks-note">{"Can be opened" if saved else "Save songs first"}</div></div>', unsafe_allow_html=True)

if active_page == "🎵 Songs":
    st.markdown('<div class="ks-kicker">Service builder</div><div class="ks-title">Songs</div><div class="ks-subtitle">Tap the search box to open the keyboard, type a title, then choose the song from the dropdown.</div>', unsafe_allow_html=True)

    # This genuine input field ensures the mobile keyboard opens on tap.
    search_query = st.text_input(
        "Search song library",
        placeholder="Tap here and type a song title...",
        key="song_search_query",
    )
    query = search_query.strip().casefold()
    matching_ids = [doc_id for doc_id in all_ids if query in file_by_id[doc_id]["name"].casefold()] if query else all_ids

    # This is the dropdown. It updates to show only matching songs.
    song_to_add = st.selectbox(
        "Matching songs",
        options=matching_ids[:50],
        index=None,
        format_func=lambda doc_id: file_by_id[doc_id]["name"],
        placeholder="Open dropdown and select a song...",
        key="song_result_choice",
        disabled=not matching_ids,
    )
    if query and not matching_ids:
        st.warning("No songs match this search.")

    if st.button("＋ Add selected song", type="primary", use_container_width=True, disabled=song_to_add is None):
        if song_to_add not in st.session_state.ordered_song_ids:
            st.session_state.ordered_song_ids.append(song_to_add)
            st.success(f"Added: {file_by_id[song_to_add]['name']}")
        else:
            st.info("That song is already selected.")

    st.subheader("Selected songs")
    if not st.session_state.ordered_song_ids:
        st.info("No songs selected yet.")
    else:
        labels, label_to_id, counts = [], {}, {}
        for doc_id in st.session_state.ordered_song_ids:
            name = file_by_id[doc_id]["name"]
            counts[name] = counts.get(name, 0) + 1
        for doc_id in st.session_state.ordered_song_ids:
            name = file_by_id[doc_id]["name"]
            label = name if counts[name] == 1 else f"{name} ({doc_id[-5:]})"
            labels.append(label); label_to_id[label] = doc_id
        sorted_labels = sort_items(labels, direction="vertical", custom_style="""
        .sortable-component{display:flex;flex-direction:column;gap:10px;padding:4px;background:transparent}
        .sortable-item{padding:14px 16px;border:1px solid #e5e7eb;border-radius:14px;background:#fff;color:#202124;box-shadow:0 3px 12px rgba(17,24,39,.05);font-size:15px;font-weight:650;cursor:grab}
        .sortable-item:before{content:'☰  ';color:#6b7280}
        """, key="service_order_sortable")
        st.session_state.ordered_song_ids = [label_to_id[label] for label in sorted_labels]

        remove_id = st.selectbox("Remove a song", st.session_state.ordered_song_ids, index=None, format_func=lambda doc_id: file_by_id[doc_id]["name"], placeholder="Select a song to remove...")
        if st.button("Remove selected song", disabled=remove_id is None):
            st.session_state.ordered_song_ids.remove(remove_id)
            st.rerun()

    if st.button("💾 Save service order", type="primary", use_container_width=True, disabled=not st.session_state.ordered_song_ids):
        save_shared_selection(google_docs, st.session_state.ordered_song_ids)
        st.cache_data.clear()
        st.success("The service order has been saved.")

if active_page == "🎥 Presentation":
    st.markdown('<div class="ks-kicker">Ready to present</div><div class="ks-title">Presentation</div><div class="ks-subtitle">Open presentation mode or download the compiled PDF.</div>', unsafe_allow_html=True)
    selected_files = get_selected_files(google_docs, get_shared_selection())
    if not selected_files:
        st.info("Add songs and save the service order first.")
    else:
        ids = tuple(str(file["id"]) for file in selected_files)
        times = tuple(str(file.get("modifiedTime", "")) for file in selected_files)
        with st.spinner("Creating the presentation..."):
            pdf_bytes = compile_pdf_cached(ids, times)
        c1, c2 = st.columns(2)
        with c1: st.link_button("🎥 Open presentation", "?view=presentation", type="primary", use_container_width=True)
        with c2: st.download_button("⬇ Download combined PDF", pdf_bytes, OUTPUT_FILE_NAME, "application/pdf", use_container_width=True)
