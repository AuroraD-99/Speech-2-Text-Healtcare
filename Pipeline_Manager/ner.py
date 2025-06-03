from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
import os
from dotenv import load_dotenv
from log import Logger


class NER:
    def __init__(self, ner_model_path="assets/HUMADEX/italian_medical_ner"):
        # Load environment variables from .env file
        load_dotenv()
        
        self.logger = Logger(self.__class__.__name__).get_logger()
        
        self.ner_model_path = ner_model_path or os.getenv("NER_MODEL")
        self.model_name = "HUMADEX/italian-medical-ner"
        
        if not os.path.exists(self.ner_model_path):
            os.makedirs(self.ner_model_path, exist_ok=True)
            self.logger.info(f"Creating directory for NER model at {self.ner_model_path}")
            tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            model = AutoModelForTokenClassification.from_pretrained(self.model_name)
            tokenizer.save_pretrained(self.ner_model_path)
            model.save_pretrained(self.ner_model_path)
        else:
            self.logger.info(f"Using existing NER model at {self.ner_model_path}")


        if not self.ner_model_path:
            raise ValueError("NER model path must be provided or set in the environment variable 'NER_MODEL'.")

        # Initialize the tokenizer and model for NER
        self.ner_tokenizer = AutoTokenizer.from_pretrained(self.ner_model_path)
        self.ner_model = AutoModelForTokenClassification.from_pretrained(self.ner_model_path)
        self.ner_pipeline = pipeline("ner", model=self.ner_model, tokenizer=self.ner_tokenizer, aggregation_strategy="simple")
        
        
    def extract_medical_entities(self, text):
        """
        Estrae entità mediche dal testo utilizzando il modello NER.
        """
        
        if not text:
            raise ValueError("Input text cannot be empty.")

        # Esegui il riconoscimento delle entità
        ner_results = self.ner_pipeline(text)

        return [(entity['word'], entity['entity_group']) for entity in ner_results]
    
    
    

if __name__ == "__main__":
    # Example usage
    ner = NER()
    
    #Ottieni il testo da analizzare dal file referto_di_prova.txt
    with open("referto_di_prova.txt", "r", encoding="utf-8") as file:
        text = file.read()
    
    entities = ner.extract_medical_entities(text)
    print(entities)