def extract_json_from_response(response_str: str) -> str:
    start = response_str.find("{")
    end = response_str.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("JSON non trovato nella risposta")
    return response_str[start:end+1]


if __name__ == "__main__":
    example_json = """Scheda di ammissione al pronto soccorso:
{
  "Chiamata": {
    "data": [
      "14:30"
    ],
    "H chiamata": "14:32",
    "H partenza": "N/A",
    "H sul posto": "15:06",
    "H partenza posto": "15:17",
    "H in PS": "15:22",
    "H libero e operativo": "15:49",
    "luogo intervento": "N/A",
    "condizione riferita": "N/A"
  },
  "Ambulanza": {
    "CRI": "N/A",
    "Sel": "N/A"
  },
  "Equipaggio": {
    "Aut.": "N/A",
    "Socc1": "N/A",
    "Socc2": "N/A",
    "IP": "N/A",
    "Medico": "N/A"
  },
  "Causa trasporto non effettuato": [
    "N/A"
  ],
  "Attivazioni/Autorità presenti": {
    "descrizione": "N/A",
    "referto": "N/A"
  },
  "Decesso": {
    "Ora decesso": "",
    "Firma": "N/A"
  },
  "Rifiuto (firma dell'interessato)": {
    "Firma": "N/A"
  },
  "Rilevazioni": {
    "Parametri": {
      "Coscienza": "N/A",
      "Cute": "N/A",
      "Respiro": "N/A",
      "Sp02": "N/A",
      "FC bpm": "N/A",
      "PA mmHg": "N/A",
      "Glic, Mg/dl": "N/A",
      "Temp. C°": "N/A"
    },
    "Glasgow Coma Scale": {
      "Apertura occhi": "N/A",
      "Risposta verbale": "N/A",
      "Risposta motoria": "N/A"
    },
    "Pupille": "N/A",
    "Lesioni riscontrate": "infarti"
  },
  "Provvedimenti": {
    "Respiro": "N/A",
    "Circolo": "N/A",
    "Immobilizzazione": "N/A",
    "Altro": "N/A",
    "Infusioni/Farmaci": "N/A"
  },
  "Annotazioni": [
    "N/A"
  ]
}
"""

print(extract_json_from_response(example_json))