from fastapi import FastAPI
from pydantic import BaseModel

from Database.mongodb import DB
from Pipeline_Manager.Pipeline_manager import PipelineManager

backend_app = FastAPI()
db = DB()

class InputText(BaseModel):
    """
    Data model for input text.
    """
    text: str

class InputReport(BaseModel):
    """
    Data model for a new report request
    """
    text:str
    anagrafica_medico:dict

@backend_app.post("/new_report")
def new_report(request: InputReport):
    """
    Endpoint to create a new clinical report.
    """
    filepath = request.text
    pipeline_manager = PipelineManager(request.anagrafica_medico)
    report_id = str(pipeline_manager.Pipeline_manager(filepath))
    return {
        "message": "New clinical report created successfully",
        "report_id": str(report_id)
        }

@backend_app.post("/delete_report")
def delete_report(report_id: str):
    """
    Endpoint to delete a clinical report by its ID.
    """
    db.delete_clinical_report(report_id)
    return {"message": f"Report with ID {report_id} deleted successfully"}

@backend_app.post("/delete_all_reports_by_patient")
def delete_all_reports_by_patient(patient_id: str):
    """
    Endpoint to delete all clinical reports for a specific patient by their ID.
    """
    db.delete_all_reports_by_patient(patient_id)
    return {"message": f"All reports for patient with ID {patient_id} deleted successfully"}


