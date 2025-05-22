import sys
import os
import re
import time
from datetime import datetime
import logging    

import json
from json2pdf_converter import generate

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class PDF_Generator:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)

        self.PDF_output = os.getenv("PDF_PATH")
        self.template_directory = os.getenv("TEMPLATE_DICTIONARY")
        self.template_name = os.getenv("TEMPLATE_NAME")
        self.output_html_path = os.getenv("OUTPUT_HTML_PATH")

    def save_FSE_to_PDF(self, JSON_output): #RICONTROLLARE + VA INSERITO IN UN FILE A PARTE
        self.logger.info("Esportazione FSE in PDF in corso ...")
        for filename in os.listdir(JSON_output):
            if filename.endswith(".json"):
                path = os.path.join(JSON_output, filename)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                output_pdf = os.path.join(self.PDF_output, filename.replace(".json", ".pdf"))

                generate(
                    json_file_path=path,
                    template_directory_path=self.template_directory,
                    output_html_path=self.output_html_path,
                    output_pdf_path=output_pdf,
                    options={
                        'encoding': 'UTF-8',
                        'margin-top': '0px',
                        'margin-right': '30px',
                        'margin-bottom': '30px',
                        'margin-left': '30px',
                        'footer-right': "Page [page] of [topage]",
                        'footer-font-size': "9",
                        'orientation': 'Portrait',
                        'page-size': 'A4',
                    },
                    template_name=self.template_name,
                    data_variables={"data": data}
                )
