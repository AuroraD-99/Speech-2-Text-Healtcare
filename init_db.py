from Database.mongodb import DB

import os
from dotenv import load_dotenv


if __name__ == "__main__":
    db = DB()
    load_dotenv("key.env", override=True)
    dataset_path = os.getenv("dataset_path")
    
    
    db.inizializza_flag(dataset_path)