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
    
    
class Controller:
    def __init__(self):
        self.logger = Logger(self.__class__.__name__).get_logger()
        
        self.app = FastAPI()
        
        # Register endpoints with the FastAPI app
        self.app.add_api_route(
            path = "/new_report",
            endpoint = self.new_report,
            methods = ["POST"],
            response_model = str,
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
        