import datetime
import io
import os
import re
import requests
import sqlite3
import time
import zipfile
from pathlib import Path
from dataclasses import dataclass
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

st.set_page_config(page_title="XI Dokumentum kereső")

# Constants
DATABASE_PATH = Path("./onkorm.db")
txt_folder = Path("./txt")
root_folder = Path("./downloads")

@dataclass
class Onkorm:
    name: str
    base_url: str

ujbuda = Onkorm(
    name="Újbuda",
    base_url="https://mikrodat.ujbuda.hu/app/cms/api/honlap"
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
    case_sensitive = st.sidebar.checkbox("Kis- és nagybetű érzékeny", value=False)
    exact_match = st.sidebar.checkbox("Pontos egyezés", value=False)
    search_button = st.sidebar.button("Keresés")

    unique_names = sorted({entry["name"] for entry in mappa_data})
    select_all = st.sidebar.checkbox("Mind kiválasztása", value=True)
    selected_names = st.sidebar.multiselect(
        "Név szerinti szűrés",
        unique_names,
        default=unique_names if select_all else [],
    )

    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = rf"\b{re.escape(search_text)}\b" if exact_match else re.escape(search_text)
    regex = re.compile(pattern, flags)

    if search_button:
        # Perform Search
        start_time = time.time()
        results = []
        total_files = 0
        matched_files = set()

        for folder in os.listdir(txt_folder):
            folder_path = os.path.join(txt_folder, folder)

            for subfolder in os.listdir(folder_path):
                subfolder_path = os.path.join(folder_path, subfolder)

                for file in os.listdir(subfolder_path):
                    file_path = os.path.join(subfolder_path, file)
                    total_files += 1

                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    for i, line in enumerate(lines):
                        if regex.search(line):
                            matched_files.add(file_path)
                            start, end = max(0, i - 3), min(len(lines), i + 4)
                            context = "".join(lines[start:end]).strip()

                            napi_entry = next(
                                (n for n in napi_data if n["uuid"] == subfolder), None
                            )
                            if napi_entry:
                                mappa_entry = next(
                                    (m for m in mappa_data if m["folder_uuid"] == folder),
                                    None,
                                )

                                if mappa_entry and mappa_entry["name"] in selected_names:
                                    results.append(
                                        {
                                            "dátum": mappa_entry["datum"],
                                            "név": mappa_entry["name"],
                                            "napirendi pont": napi_entry["targy"],
                                            "file": file,
                                            "context": context,
                                        }
                                    )
                            break

        results.sort(key=lambda x: datetime.datetime.strptime(x["dátum"], "%Y.%m.%d."))

        end_time = time.time()
        elapsed_time = end_time - start_time
        percentage_matched = (len(matched_files) / total_files) * 100 if total_files else 0

        st.write("""A nyilvánosan nem elérhető előterjesztési dokumentumok, 
        illetve a döntési javaslatok és azok mellékletei nem szerepelnek az adatbázisban.""")
        st.divider()

        st.write(f"Feldolgozott fájlok száma: {total_files}")
        st.write(f"Találatok: {len(matched_files)} fájl ({percentage_matched:.2f}%)")
        st.write(f"Feldolgozási idő: {elapsed_time:.2f} másodperc")

        if results:
            df_results = pd.DataFrame(results)

            # Group results by month and count matches
            df_results['dátum'] = pd.to_datetime(df_results['dátum'], format='%Y.%m.%d.')
            df_results['month_year'] = df_results['dátum'].dt.to_period('M')
            matches_over_time = df_results.groupby('month_year').size().reset_index(name='match_count')

            # Convert 'month_year' back to string for better display
            matches_over_time['month_year'] = matches_over_time['month_year'].astype(str)

            # Display the data as a bar chart
            st.subheader("Találatok száma idő szerint")
            st.write("A találatok havi bontásban")
            st.bar_chart(matches_over_time.set_index('month_year')['match_count'])

            # Create Excel file
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
                df_results.to_excel(writer, index=False, sheet_name="Eredmények")
            excel_data = excel_buffer.getvalue()

            st.download_button(
                label="Eredmények letöltése Excel formátumban",
                data=excel_data,
                file_name=f"keresesi_eredmenyek_{search_text}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            for result in results:
                st.subheader(f"{result['dátum']}")
                st.write(f"**{result['név']}**")
                st.write(f"**Napirendi pont:** {result['napirendi pont']}")
                st.write(f"**Szövegkörnyezet:** (...) {result['context']} (...)")
                st.write(f"Fájl: {result['file']}")
        else:
            st.write("Nincs találat a keresési feltételek alapján.")


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
                (i["uuid"] for i in folder_year_json["content"] if i["datum"] == target_date),
                None
            )

            if not folder_uuid:
                st.error("A megadott dátumhoz nincs elérhető mappa!")
            else:
                st.write(f"Mappa UUID: {folder_uuid}")
                folder_path = root_folder / folder_uuid
                os.makedirs(folder_path, exist_ok=True)

                # Fetch Folder Details
                folder_detail_url = f"{ujbuda.base_url}/detail?id={folder_uuid}"
                folder_detail_json = requests.get(folder_detail_url, verify=False)
                session_type = folder_detail_json.json()["content"]["nev"]
                session_uuid = folder_detail_json.json()["content"]["uuid"]
                
                st.write(folder_detail_json.json())
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
                doc_uuid_list = [
                    point["uuid"]
                    for point in agenda_json.json()["content"]
                    if point["nyilvanossagjelolo"] != "1"
                ]

                # Download Files
                for doc_uuid in doc_uuid_list:
                    body_dok_url = f"{ujbuda.base_url}/elo/djav?uuid={folder_uuid}&uuid2={doc_uuid}"
                    body_file_json = requests.get(body_dok_url, verify=False)

                    if not body_file_json.json()['content']:
                        continue

                    file_name = body_file_json.json()["content"][0]["name"]
                    file_uuid = body_file_json.json()["content"][0]["uuid"]
                    file_download_url = f"{ujbuda.base_url}/getfile/{file_uuid}/{file_name}"
                    file_response = requests.get(file_download_url)

                    save_path = folder_path / file_name
                    with open(save_path, "wb") as file:
                        file.write(file_response.content)

                # Create ZIP Archive
                zip_name = target_date.replace(".", "_") + ".zip"
                zip_archive = root_folder / zip_name
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
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        os.remove(os.path.join(root, file))
                os.rmdir(folder_path)
                os.remove(zip_archive)
                st.success("Feldolgozás és tisztítás befejezve!")

