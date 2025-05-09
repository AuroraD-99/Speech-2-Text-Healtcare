import streamlit as st
import os 
import sys
import requests
from PIL import Image
import dotenv



sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from log import Logger

class Dashboard:
    def __init__(self, env_file = "key.env"):
        """
        Initializes the dashboard pipeline by loading environment variables 
        and setting up the logger and session state.
        
        Args:
            env_file (str): The path to the environment file containing necessary credentials and configurations.
        
        Raises:
            Exception: If environment variables cannot be loaded or other initialization errors occur.
        """
        
        dotenv.load_dotenv(env_file, override=True)
        self.logger = Logger(self.__class__.__name__).get_logger()
        #self.logo = os.getenv('AI_IMAGE_UI')
        #self.controller_url = os.getenv('CONTROLLER_API_URL', 'http://127.0.0.1:8003')
        # Load image into the sidebar
        #self.image_sidebar = Image.open(self.logo)

        # Initialize session state
        #self._initialize_session_state()
        
        self.logger.info("Dashboard initialized successfully.")
        
        
    def run(self):
        """
        Runs the dashboard application, setting up the sidebar and main content.
        """
        
        