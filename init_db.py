from Database.mongodb import DB

import os
from dotenv import load_dotenv



if __name__ == "__main__":
    db = DB()
    load_dotenv("key.env", override=True)
    dataset_path = os.getenv("dataset_path")
    
    flag = db.collection('init_flag').find_one({"initialized": True})
    
    if flag:
        exit(0)
    
    if dataset_path:
        db.popola_db(dataset_path)
        db.collection('init_flag').insert_one({"initialized": True})
    else:
        print("❌ Variabile 'dataset_path' non trovata nel file .env")