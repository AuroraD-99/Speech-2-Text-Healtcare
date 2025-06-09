from Database.mongodb import DB

import os
from dotenv import load_dotenv


if __name__ == "__main__":
    load_dotenv("key.env", override=True)
    dataset_path = os.getenv("dataset_path")
    if dataset_path:
        db = DB()
        db.popola_db(dataset_path)
    else:
        print("❌ Variabile 'dataset_path' non trovata nel file .env")