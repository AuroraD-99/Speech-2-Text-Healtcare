import os
import requests
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from log import Logger
from pydantic import BaseModel




class InputText(BaseModel):
    """
    Data model for input text.
    """
    text: str

class InputReport(BaseModel):
    text: str
    anagrafica_medico: dict
    
class Controller:
    def __init__(self, env_file='key.env'):
        self.logger = Logger(self.__class__.__name__).get_logger()
        
        load_dotenv(env_file, override=True)
        self.backend_url = os.getenv('BACKEND_URL', 'http://127.0.0.1:8001')
        
        self.app = FastAPI()
        
        # Register endpoints with the FastAPI app
        self.app.add_api_route(
            path = "/new_report",
            endpoint = self.new_report,
            methods = ["POST"],
            response_model = dict,
            summary = "Create a new clinical report",
            description = "Generates a new clinical report running the pipeline in Pipeline_Manager.py",
        )
        
        self.app.add_api_route(
            path = "/delete_report",
            endpoint = self.delete_report,
            methods = ["POST"],
            response_model = str,
            summary = "Delete a clinical report",
            description = "Deletes a clinical report by its ID",
        )
        
        self.app.add_api_route(
            path = "/delete_all_reports_by_patient",
            endpoint = self.delete_all_reports_by_patient,
            methods = ["POST"],
            response_model = str,
            summary = "Delete all reports for a patient",
            description = "Deletes all clinical reports for a specific patient by their ID",
        )
    def new_report(self, input_var:InputReport):
        """
        Endpoint to create a new clinical report.
        """
        self.logger.info("Creating a new clinical report")
        try:
            response = requests.post(
                url = f"{self.backend_url}/new_report",
                json = {
                    "text": input_var.text,
                    "anagrafica_medico": input_var.anagrafica_medico
                }
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Error creating new report: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        
    def delete_report(self, report_id: str):
        """
        Endpoint to delete a clinical report by its ID.
        """
        self.logger.info(f"Deleting report with ID: {report_id}")
        try:
            response = requests.post(
                url = f"{self.backend_url}/delete_report",
                json = {"report_id": report_id}
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Error deleting report: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        
    def delete_all_reports_by_patient(self, patient_id: str):
        """
        Endpoint to delete all clinical reports for a specific patient by their ID.
        """
        self.logger.info(f"Deleting all reports for patient with ID: {patient_id}")
        try:
            response = requests.post(
                url = f"{self.backend_url}/delete_all_reports_by_patient",
                json = {"patient_id": patient_id}
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Error deleting reports for patient: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# Create an instance of the Controller class and expose the FastAPI app
load_dotenv("key.env")  # Load environment variables from .env file
controller = Controller()
app = controller.app