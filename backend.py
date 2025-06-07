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
    function_mode : str

class ReportUpdate(BaseModel):
    """
    Data model for updating a report
    """
    report_id : str
    updated_data : dict
    
    
@backend_app.post("/new_report")
def new_report(request: InputReport):
    """
    Endpoint to create a new clinical report.
    """
    filepath = request.text
    print("BACKEND: function mode selezionata: " + request.function_mode)
    pipeline_manager = PipelineManager(anagrafica_medico=request.anagrafica_medico, function_mode=request.function_mode)
    report_id = str(pipeline_manager.Pipeline_manager(filepath))
    report = db.get_report_by_id(report_id)
    report["_id"] = str(report_id)
    return {
        "message": "New clinical report created successfully",
        "report": report
        }

@backend_app.post("/delete_report")
def delete_report(report_id: InputText):
    """
    Endpoint to delete a clinical report by its ID.
    """
    db.delete_clinical_report(report_id.text)
    return {"message": f"Report with ID {report_id.text} deleted successfully"}




@backend_app.post("/get_report_by_id")
def get_report_by_id(report_id: InputText):
    """
    Endpoint to get a clinical report by its ID
    """
    report = db.get_report_by_id(report_id.text)
    report["_id"] = report_id.text
    return {"message":f"Report with ID {report_id.text} retrieved successfully", "report": report}