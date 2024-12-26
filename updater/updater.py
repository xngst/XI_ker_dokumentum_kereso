"""
XI-Files 
Több mindent, kevesebb semmit!
"""
import logging
import os
import requests
import sqlite3
import time
import pandas as pd
import shutil
import warnings
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

import fitz # pymupdf
from whoosh import index
from whoosh.index import create_in
from whoosh.fields import Schema, TEXT, ID, DATETIME

warnings.filterwarnings("ignore")

# Paths
DATABASE_PATH = Path("./data/onkorm.db")
LOG_FILE_PATH = Path("./log/download.log")
INDEX_FOLDER = Path("./data/whoosh_index_dir")
PDF_FOLDER = Path("./data/pdf")
TXT_FOLDER = Path("./data/txt")

os.makedirs(PDF_FOLDER, exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename=LOG_FILE_PATH,
    filemode="a",
)

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
    db_file_detail="ujbuda_file_det"
)

def fetch_data_from_db(database_path, table_name):
    with sqlite3.connect(database_path) as conn:
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql_query(query, conn)
    return df

def fetch_json(url):
    try:
        response = requests.get(url, verify=False, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Failed to fetch data from {url}: {e}")
        return None

def insert_into_table(conn, table_name, data):
    try:
        cursor = conn.cursor()
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?'] * len(data))
        values = tuple(data.values())
        insert_query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        cursor.execute(insert_query, values)
        conn.commit()
    except sqlite3.Error as e:
        print(e)
        logging.error(f"Database error while inserting values {values}: {e}")
          

### 1) fetch folder uuid from db

folder_df = fetch_data_from_db(DATABASE_PATH,ujbuda.db_folder)
db_folder_uuid = folder_df['folder_uuid']
print(f"Len of db_folder_uuid: {len(db_folder_uuid)}")

### 2) fetch folder uuid from api
          
year_url = f"{ujbuda.base_url}/inv/years"
inv_year_r = requests.get(year_url, verify=False)
years = inv_year_r.json()['content']

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

collector_df = pd.DataFrame()

for year in years:
    
    folder_year_url = f"{ujbuda.base_url}/inv/folders?year={year}"
    folder_year_response = requests.get(folder_year_url, verify=False)
    
    folder_data = folder_year_response.json()['content']
    folder_df = pd.DataFrame(folder_data)
    folder_df.columns = ['datum', 'nyilvanossagjelolo', 'kategoria', 'idopont', 'hely', 'folder_uuid']
    
    collector_df = pd.concat([collector_df,folder_df],ignore_index=True)

api_folder_uuid = collector_df['folder_uuid']

missing_uuid = list(set(api_folder_uuid) - set(db_folder_uuid))
missing_df = collector_df[collector_df["folder_uuid"].isin(missing_uuid)]


##########testing##################
#db_folder_uuid = db_folder_uuid.iloc[1:]
#missing_uuid = list(set(api_folder_uuid) - set(db_folder_uuid))
#missing_df = collector_df[collector_df["folder_uuid"].isin(missing_uuid)]
##########testing##################

if len(missing_df) > 0:
    print(f"Len of missing_df: {len(missing_df)}")
    print(missing_df)
else:
    print("No new documents")

for folder_uuid in missing_df["folder_uuid"]:
    
    logging.info(f"Processing folder: {folder_uuid}")

    # Fetch folder details
    folder_detail_url = f"{ujbuda.base_url}/detail?id={folder_uuid}"
    folder_detail_data = fetch_json(folder_detail_url)
    if not folder_detail_data:
        logging.error(f"Failed to fetch folder details for UUID {folder_uuid}")
        continue

    folder_details = folder_detail_data.get("content", {})
    if not folder_details:
        logging.warning(f"No details found for folder UUID {folder_uuid}")
        continue

    folder_details["folder_uuid"] = folder_uuid
    agenda_uuid = folder_details.pop("uuid", None)

    if "nev" in folder_details:
        folder_details["name"] = folder_details.pop("nev")

    # Update folder details in the database
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            values = ", ".join([f"{key} = ?" for key in folder_details if key != "folder_uuid"])
            sql = f"UPDATE {ujbuda.db_folder} SET {values} WHERE folder_uuid = ?"
            cursor.execute(sql, tuple(folder_details[key] for key in folder_details if key != "folder_uuid") + (folder_uuid,))
            conn.commit()
    except sqlite3.DatabaseError as e:
        logging.error(f"Database error while updating folder UUID {folder_uuid}: {e}")
        continue

    session_type = folder_details.get("name", "").lower()

    # Determine agenda URL
    if "bizottság" in session_type:
        agenda_url = f"{ujbuda.base_url}/inv/list?id={folder_uuid}&id2={agenda_uuid}"
    elif session_type == "képviselő-testület":
        agenda_url = f"{ujbuda.base_url}/inv/listtest?id={folder_uuid}"
    else:
        logging.warning(f"Unknown session type for folder {folder_uuid}")
        continue

    # Fetch agenda data
    agenda_data = fetch_json(agenda_url)
    if not agenda_data or not agenda_data.get("content"):
        logging.info(f"No agenda data for folder {folder_uuid}")
        continue

    for agenda_item in agenda_data["content"]:
        agenda_item["folder_uuid"] = folder_uuid
        uuid = agenda_item.get("uuid")
        if not uuid:
            logging.warning(f"Agenda item missing UUID for folder {folder_uuid}")
            continue

        # Insert agenda item into the database
        try:
            with sqlite3.connect(DATABASE_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT 1 FROM {ujbuda.db_napirendi} WHERE uuid = ?", (uuid,))
                if not cursor.fetchone():
                    columns = list(agenda_item.keys())
                    placeholders = ", ".join(["?"] * len(columns))
                    sql = f"INSERT INTO {ujbuda.db_napirendi} ({', '.join(columns)}) VALUES ({placeholders})"
                    cursor.execute(sql, tuple(agenda_item[col] for col in columns))
                    conn.commit()
        except sqlite3.DatabaseError as e:
            logging.error(f"Database error while inserting agenda item UUID {uuid}: {e}")
            continue

    # Process files for agenda items
    for agenda_item in agenda_data["content"]:
        if agenda_item.get("napirend") == "0":
            # Skip downloading the invite
            continue

        file_name = agenda_item.get("name")
        agenda_uuid = agenda_item.get("uuid")
        if not file_name or not agenda_uuid:
            logging.warning(f"Missing file_name or agenda_uuid for folder {folder_uuid}")
            continue

        body_dok_url = f"{ujbuda.base_url}/elo/djav?uuid={folder_uuid}&uuid2={agenda_uuid}"
        try:
            body_file_json = fetch_json(body_dok_url)
            if not body_file_json or not body_file_json.get("content"):
                logging.warning(f"No file content for agenda {agenda_uuid}")
                continue
        except Exception as e:
            logging.error(f"Error fetching files for agenda UUID {agenda_uuid}: {e}")
            continue
            
        #insert file
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            for file_item in body_file_json.get("content", []):
                file_item["folder_uuid"] = folder_uuid
                file_item["agenda_uuid"] = agenda_uuid
                file_uuid = file_item.get("uuid")
                cursor.execute(f"SELECT 1 FROM {ujbuda.db_file_detail} WHERE uuid = ?", (file_uuid,))
                if not cursor.fetchone():
                    insert_into_table(conn,ujbuda.db_file_detail,file_item)
                    logging.info(f"{file_uuid} added to database")
                else:
                    logging.error(f"{file_uuid} already in database")          
            
        for file_item in body_file_json.get("content", []):
            
            file_name = file_item.get("name")
            file_uuid = file_item.get("uuid")
            
            if not file_name or not file_uuid:
                logging.warning(f"Missing file details for agenda UUID {agenda_uuid}")
                continue

            file_download_url = f"{ujbuda.base_url}/getfile/{file_uuid}/{file_name}"
            save_path = PDF_FOLDER / folder_uuid / agenda_uuid / file_name

            # Download and save file
            try:
                file_response = requests.get(file_download_url, timeout=10)
                file_response.raise_for_status()
                os.makedirs(save_path.parent, exist_ok=True)
                with open(save_path, "wb") as file:
                    file.write(file_response.content)
                logging.info(f"Downloaded file {file_name} for agenda {agenda_uuid}")
            except requests.RequestException as e:
                logging.error(f"Error downloading file {file_name}: {e}")
                continue

            # Convert to text and save
            try:
                with fitz.open(save_path) as doc:
                    txt_path = TXT_FOLDER / folder_uuid / agenda_uuid / file_name.replace(".pdf", ".txt")
                    os.makedirs(txt_path.parent, exist_ok=True)
                    with open(txt_path, "wb") as out:
                        for page in doc:
                            text = page.get_text().encode("utf8")
                            out.write(text)
                            out.write(bytes((12,)))
                    logging.info(f"Converted PDF to text: {txt_path}")
            except Exception as e:
                logging.error(f"Error converting file {file_name} to text: {e}")

#Clean up pdf folder
shutil.rmtree(PDF_FOLDER)       

#Reindex
if len(missing_df) > 0:

    print("Reindexing")

    if INDEX_FOLDER.exists() and INDEX_FOLDER.is_dir():
        shutil.rmtree(INDEX_FOLDER)

    os.makedirs(INDEX_FOLDER, exist_ok=True)

    schema = Schema(file_name=TEXT(stored=True),
                    date=DATETIME(stored=True,sortable=True),
                    folder_uuid=ID(stored=True),
                    agenda_uuid=ID(stored=True),
                    content=TEXT)

    ix = create_in(INDEX_FOLDER, schema)

    writer = ix.writer()

    for folder_uuid in os.listdir(TXT_FOLDER):

        with sqlite3.connect(DATABASE_PATH) as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {ujbuda.db_folder} WHERE folder_uuid='{folder_uuid}'")
            folder_details = cur.fetchone()
            date = datetime.strptime(folder_details[2],'%Y.%m.%d.')

        for agenda_uuid in os.listdir(TXT_FOLDER/folder_uuid):

            for file in os.listdir(TXT_FOLDER/folder_uuid/agenda_uuid):
                with open(TXT_FOLDER/folder_uuid/agenda_uuid/file,"r") as f:
                    content = " ".join([i.strip().replace("/n","") for i in f.readlines() if i.strip()])

                writer.add_document(file_name=file,
                                    date=date,
                                    folder_uuid=folder_uuid,
                                    agenda_uuid=agenda_uuid,
                                    content=content
                                   )
    writer.commit()

