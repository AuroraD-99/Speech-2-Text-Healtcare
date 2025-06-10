from Pipeline_Manager.Pipeline_manager import PipelineManager
from Database.mongodb import DB
from fastapi import FastAPI
import requests
from dotenv import load_dotenv
import os
import pytest


class PipelineTest:
    def __init__(self, anagrafica_medico="", function_mode="Emergency", env_file="key.env"):
        self.pipeline_manager = PipelineManager(anagrafica_medico, function_mode, env_file)
        self.db = DB()
        load_dotenv(env_file, override=True)
        self.controller_url = os.getenv("CONTROLLER", "http://localhost:8003")
        self.anagrafica_medico = anagrafica_medico = {
            "Anagrafica": {
            "Email": "anna.quercia@fintoemail.it",
            "Nome": "Anna",
            "Cognome": "Quercia",
            "Cellulare": "3331234567",
            "Codice Fiscale": "QRCSNN80A41H501U",
            "Ruolo": "Medico"
            },
            "Ospedale": {
            "Nome Ospedale": "Ospedale Maggiore",
            "Città": "Bologna",
            "Provincia": "BO",
            "CAP": "40138",
            "Reparto": "Cardiologia"
            }
        }
        
    def new_report(self, filename, anagrafica_medico=None):
        """
        Create a new report in the database.
        """
        func_mode = self.pipeline_manager.function_mode
        response = requests.post(
            url=f"{self.controller_url}/new_report",
            json = {
                "text": filename,
                "anagrafica_medico": anagrafica_medico,
                "function_mode": func_mode,
            })
        
        assert response.status_code == 200, "Failed to create a new report"
        if response.status_code == 200:
            report = response.json()
        
        print("Test report creation successful:")
        
        return report["report"].get("_id")

        
    
    def test_pipeline_initialization(self):
        """
        Test to ensure the pipeline initializes correctly.
        """
        assert self.pipeline_manager is not None, "PipelineManager should be initialized"
        assert self.db is not None, "Database connection should be established"
        
        print("Test pipeline initialization successful.")
        
    def test_pipeline_run(self):
        """
        Test to ensure the pipeline runs without errors.
        """
        
        
        
        # Ipotizzando l'esistenza di un file audio di test
        audio_file_path = "./assets/audios/test_audio.wav"
        
        id_report = self.new_report(audio_file_path, self.anagrafica_medico)
        
        assert id_report is not None, "Pipeline should return a valid report ID"
        return id_report
    
    def teardown(self, report_id):
        """
        Clean up resources after tests.
        """
        self.db.delete_clinical_report(report_id)
        self.pipeline_manager = None
        self.db = None
        
    def run_all_tests(self):
        """
        Run all tests in the pipeline.
        """
        self.test_pipeline_initialization()
        report_id = self.test_pipeline_run()
        self.teardown(report_id)
        print("All tests passed successfully.")
        
        
class DBTest:
    def __init__(self):
        self.db = DB()
        self.anagrafica_medico = {
            "Anagrafica": {
            "Email": "anna.quercia@fintoemail.it",
            "Nome": "Anna",
            "Cognome": "Quercia",
            "Cellulare": "3331234567",
            "Codice Fiscale": "QRCSNN80A41H501U",
            "Ruolo": "Medico"
            },
            "Ospedale": {
            "Nome Ospedale": "Ospedale Maggiore",
            "Città": "Bologna",
            "Provincia": "BO",
            "CAP": "40138",
            "Reparto": "Cardiologia"
            }
        }
    
    def test_db_connection(self):
        """
        Test to ensure the database connection is established.
        """
        assert self.db is not None, "Database connection should be established"
        
    def insert_report_test(self):
        """
        Test to retrieve a report from the database.
        """
    
        report_id = "test_report_id"
        report = {
            "dati medico": self.anagrafica_medico,
        }
        
        
        inserted_id = self.db.insert_clinical_report(report_id, report)
        
        
        assert inserted_id is not None, "Report should be inserted successfully"
        
        retrieved_report = self.db.get_report_by_id(inserted_id)
        
        assert retrieved_report is not None, "Report should be retrievable from the database"
    
    def teardown(self, report_id):
        """
        Clean up resources after tests.
        """
        self.db.delete_clinical_report(report_id)
        self.db = None
        
    def run_all_tests(self):
        """
        Run all tests in the database.
        """
        self.test_db_connection()
        self.insert_report_test()
        self.teardown("test_report_id")
        

if __name__ == "__main__":
    # Run Pipeline Tests
    pipepine_test = PipelineTest()
    pipepine_test.run_all_tests()
    
    # Run Database Tests
    db_test = DBTest()
    db_test.run_all_tests()