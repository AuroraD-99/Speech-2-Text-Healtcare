from typing import List, Optional
from pydantic import BaseModel, Field



class Chiamata(BaseModel):
    data: List[str]
    H_chiamata: str
    H_partenza: str
    H_sul_posto: str
    H_partenza_posto: str
    H_in_PS: str
    H_libero_e_operativo: str
    luogo_intervento: str
    condizione_riferita: str

class Ambulanza(BaseModel):
    CRI: str
    Sel: str

class Equipaggio(BaseModel):
    Aut_: str
    Socc1: str
    Socc2: str
    IP: str
    Medico: str

class AttivazioniAutorita(BaseModel):
    descrizione: str
    referto: str

class Decesso(BaseModel):
    Ora_decesso: str
    Firma: str

class Rifiuto(BaseModel):
    Firma: str

class Parametri(BaseModel):
    Coscienza: str
    Cute: str
    Respiro: str
    Sp02: str
    FC_bpm: str
    PA_mmHg: str
    Glic_Mg_dl: str
    Temp_C: str

class GlasgowComaScale(BaseModel):
    Apertura_occhi: str = Field(..., alias="Apertura occhi")
    Risposta_verbale: str = Field(..., alias="Risposta verbale")
    Risposta_motoria: str = Field(..., alias="Risposta motoria")

class Rilevazioni(BaseModel):
    Parametri: Parametri
    Glasgow_Coma_Scale: GlasgowComaScale = Field(..., alias="Glasgow Coma Scale")
    Pupille: str
    Lesioni_riscontrate: str

class Provvedimenti(BaseModel):
    Respiro: str
    Circolo: str
    Immobilizzazione: str
    Altro: str
    Infusioni_Farmaci: str

class SchedaPS(BaseModel):
    Chiamata: Chiamata
    Ambulanza: Ambulanza
    Equipaggio: Equipaggio
    Causa_trasporto_non_effettuato: List[str] = Field(..., alias="Causa trasporto non effettuato")
    Attivazioni_Autorità_presenti: AttivazioniAutorita = Field(..., alias="Attivazioni Autorità presenti")
    Decesso: Decesso
    Rifiuto__firma_dell_interessato: Rifiuto = Field(..., alias="Rifiuto (firma dell'interessato)")
    Rilevazioni: Rilevazioni
    Provvedimenti: Provvedimenti
    Annotazioni: List[str]
    
    
    model_config = {
        "populate_by_name": True,
        "extra": "forbid"
    }