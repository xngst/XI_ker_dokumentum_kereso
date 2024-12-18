"""
Indexelt keresés
"""
import datetime
import io
import os
import re
import requests
import shutil
import sqlite3
import time
import zipfile
from pathlib import Path
from dataclasses import dataclass
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from whoosh import index
from whoosh.qparser import QueryParser
from whoosh.query import Regex

st.set_page_config(page_title="XI Dokumentum kereső")

DATABASE_PATH = Path("./data/onkorm.db")
TXT_FOLDER = Path("./data/txt")
INDEX_FOLDER = Path("./data/whoosh_index_dir")
DOWNLOAD_FOLDER = Path("./downloads")

ix = index.open_dir(INDEX_FOLDER)


@dataclass
class Onkorm:
    """Dataclass to store configuration for Onkorm."""

    name: str
    base_url: str
    db_folder: str
    db_napirendi: str
    db_file_detail: str


ujbuda = Onkorm(
    name="Újbuda",
    base_url="https://mikrodat.ujbuda.hu/app/cms/api/honlap",
    db_folder="ujbuda_meghivo_mappa",
    db_napirendi="ujbuda_napirendi",
    db_file_detail="ujbuda_file_det",
)


# Fetch Data
def fetch_data_from_db(database_path, query):
    with sqlite3.connect(database_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


mappa_query = "SELECT * FROM ujbuda_meghivo_mappa"
napi_query = "SELECT * FROM ujbuda_napirendi"

mappa_data = fetch_data_from_db(DATABASE_PATH, mappa_query)
napi_data = fetch_data_from_db(DATABASE_PATH, napi_query)

# Sidebar Navigation
st.sidebar.title("Navigáció")
app_mode = st.sidebar.radio("Válassza ki az alkalmazást:", ["Kereső", "ZIP Letöltő"])

if app_mode == "Kereső":
    # Search Application
    st.title("Dokumentum Kereső")
    st.sidebar.header("Keresési Beállítások")

    search_text = st.sidebar.text_input("Keresendő szöveg", "")
    exact_match = st.sidebar.checkbox("Pontos egyezés", value=False)
    search_button = st.sidebar.button("Keresés")

    unique_names = sorted({entry["name"] for entry in mappa_data})
    select_all = st.sidebar.checkbox("Mind kiválasztása", value=True)
    selected_names = st.sidebar.multiselect(
        "Név szerinti szűrés",
        unique_names,
        default=unique_names if select_all else [],
    )

    def build_regex(search_text, exact_match):
        pattern = (
            rf"\b{re.escape(search_text)}\b" if exact_match else re.escape(search_text)
        )
        return re.compile(pattern)

    if search_text or search_button:
        st.divider()
        with ix.searcher() as searcher:
            start_time = time.time()
            regex = build_regex(search_text, exact_match=exact_match)
            # query = QueryParser("content", ix.schema).parse(regex)
            query = Regex("content", regex.pattern)
            results = searcher.search(query, limit=None, sortedby="date", reverse=True)
            matched_files = results.scored_length()
            total_files = searcher.doc_count_all()
            end_time = time.time()
            elapsed_time = end_time - start_time
            percentage_matched = (
                (matched_files / total_files) * 100 if total_files else 0
            )

            st.write(
                """A nyilvánosan nem elérhető előterjesztési dokumentumok, 
		    illetve a döntési javaslatok és azok mellékletei nem szerepelnek az adatbázisban."""
            )
            st.divider()

            st.write(f"Feldolgozott fájlok száma: {total_files}")
            st.write(
                f"Találatok: {matched_files} dokumentum ({percentage_matched:.2f}%)"
            )
            st.write(f"Feldolgozási idő: {elapsed_time:.2f} másodperc")
            st.divider()

            for result in results:
                with sqlite3.connect(DATABASE_PATH) as conn:
                    cur = conn.cursor()

                    agenda_uuid = result["agenda_uuid"]
                    folder_uuid = result["folder_uuid"]

                    cur.execute(
                        f"SELECT * FROM {ujbuda.db_folder} WHERE folder_uuid='{folder_uuid}'"
                    )
                    folder_details = cur.fetchone()
                    session_type = folder_details[3]
                    file_path = Path(
                        TXT_FOLDER
                        / result["folder_uuid"]
                        / result["agenda_uuid"]
                        / result["file_name"]
                    )
                    if session_type in selected_names:
                        cur.execute(
                            f"SELECT * FROM {ujbuda.db_napirendi} WHERE uuid='{agenda_uuid}'"
                        )
                        agenda_details = cur.fetchone()
                        st.write(f"{session_type}")
                        # st.write(file_path)
                        st.write(f"Dátum: {result['date'].strftime('%Y %m %d')}")
                        st.write(f"Napirendi pont: {agenda_details[3]}")

                        with open(file_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                            for i, line in enumerate(lines):
                                if regex.search(line):
                                    start, end = max(0, i - 3), min(len(lines), i + 4)
                                    context = "".join(lines[start:end]).strip()
                                    break
                        st.write("Szövegkontextus: ")
                        st.code(context)
                        st.divider()


elif app_mode == "ZIP Letöltő":
    # ZIP Downloader Application
    st.title("ZIP Letöltő")
    st.sidebar.header("Dátum alapú letöltés")

    # Fetch Dates for Dropdown
    year = datetime.datetime.now().year
    folder_year_url = f"{ujbuda.base_url}/inv/folders?year={year}"

    st.write("Dátumok betöltése...")
    response = requests.get(folder_year_url, verify=False)
    if response.status_code == 200:
        available_dates = [entry["datum"] for entry in response.json()["content"]]
        selected_date = st.sidebar.selectbox("Válasszon dátumot:", available_dates)
    else:
        st.sidebar.error("Nem sikerült lekérni a dátumokat!")
        available_dates = []
        selected_date = None

    if selected_date:
        download_button = st.sidebar.button("Letöltés és Csomagolás")

        if download_button:
            target_date = selected_date
            folder_year_json = response.json()
            folder_uuid = next(
                (
                    i["uuid"]
                    for i in folder_year_json["content"]
                    if i["datum"] == target_date
                ),
                None,
            )

            if not folder_uuid:
                st.error("A megadott dátumhoz nincs elérhető mappa!")
            else:
                st.write(f"Mappa UUID: {folder_uuid}")
                folder_path = DOWNLOAD_FOLDER / folder_uuid
                os.makedirs(folder_path, exist_ok=True)

                # Fetch Folder Details
                folder_detail_url = f"{ujbuda.base_url}/detail?id={folder_uuid}"
                folder_detail_json = requests.get(folder_detail_url, verify=False)
                session_type = folder_detail_json.json()["content"]["nev"]
                session_uuid = folder_detail_json.json()["content"]["uuid"]

                st.write(session_type)

                # Determine API Routes
                if "Bizottság" in session_type:
                    body_agenda_url = f"{ujbuda.base_url}/inv/list?id={folder_uuid}&id2={session_uuid}"
                    invite_url = f"{ujbuda.base_url}/inv/biz?id={folder_uuid}"
                elif session_type == "Képviselő-testület":
                    body_agenda_url = f"{ujbuda.base_url}/inv/listtest?id={folder_uuid}"
                    invite_url = f"{ujbuda.base_url}/inv/test?id={folder_uuid}"

                # Get Agenda Points
                st.write(body_agenda_url)
                agenda_json = requests.get(body_agenda_url, verify=False)
                # st.write(agenda_json.json())
                doc_uuid_list = [
                    point["uuid"]
                    for point in agenda_json.json()["content"]
                    if point["nyilvanossagjelolo"] != "1"
                ]

                public_docs = [
                    i["name"]
                    for i in agenda_json.json().get("content")
                    if i["nyilvanossagjelolo"] != "1"
                ]
                not_public_docs = [
                    i["name"]
                    for i in agenda_json.json().get("content")
                    if i["nyilvanossagjelolo"] == "1"
                ]

                st.write("Nyilvános dokumentumok:")
                st.write(public_docs)
                st.write("Nem nyilvános dokumentumok:")
                st.write(not_public_docs)

                # Download Files
                for doc_uuid in doc_uuid_list:
                    body_dok_url = f"{ujbuda.base_url}/elo/djav?uuid={folder_uuid}&uuid2={doc_uuid}"
                    body_file_json = requests.get(body_dok_url, verify=False)

                    if not body_file_json.json()["content"]:
                        continue

                    # 9) Save pdfs
                    for file_item in body_file_json.json().get("content", []):
                        file_name = file_item.get("name")
                        file_uuid = file_item.get("uuid")

                        file_download_url = (
                            f"{ujbuda.base_url}/getfile/{file_uuid}/{file_name}"
                        )

                        file_response = requests.get(file_download_url, timeout=10)
                        file_response.raise_for_status()
                        save_path = folder_path / file_name

                    with open(save_path, "wb") as file:
                        file.write(file_response.content)

                # Create ZIP Archive
                zip_name = target_date.replace(".", "_") + ".zip"
                zip_archive = DOWNLOAD_FOLDER / zip_name
                with zipfile.ZipFile(zip_archive, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(folder_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, start=folder_path)
                            zipf.write(file_path, arcname)

                # Provide ZIP for Download
                with open(zip_archive, "rb") as zip_file:
                    st.download_button(
                        label="Letöltés ZIP formátumban",
                        data=zip_file,
                        file_name=zip_name,
                        mime="application/zip",
                    )

                # Clean Up
                shutil.rmtree(folder_path)
                os.remove(zip_archive)
                st.success("Feldolgozás és tisztítás befejezve!")
