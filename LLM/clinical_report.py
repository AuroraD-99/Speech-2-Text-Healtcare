from pydantic import BaseModel, Field
from typing import Optional

class Intestazione(BaseModel):
    data_visita: str = Field(..., alias="Data visita")
    ora_visita: str = Field(..., alias="Ora visita")
    ambulatorio: str = Field(..., alias="Ambulatorio")
    medico: str = Field(..., alias="Medico")

class Anamnesi(BaseModel):
    personale: str = Field(..., alias="Personale")
    familiare: str = Field(..., alias="Familiare")
    evento_attuale: str = Field(..., alias="Evento attuale")

class RefertoClinico(BaseModel):
    intestazione: Intestazione = Field(..., alias="Intestazione")
    motivo_della_visita: str = Field(..., alias="Motivo della visita")
    anamnesi: Anamnesi = Field(..., alias="Anamnesi")
    esame_obiettivo: str = Field(..., alias="Esame obiettivo")
    esami_eseguiti: str = Field(..., alias="Esami eseguiti")
    diagnosi: str = Field(..., alias="Diagnosi")
    terapia: str = Field(..., alias="Terapia")
    follow_up: str = Field(..., alias="Follow-up")
    firma_medico: str = Field(..., alias="Firma medico")
    data_redazione: str = Field(..., alias="Data redazione")

    model_config = {
        "populate_by_name": True,
        "extra": "forbid"
    }