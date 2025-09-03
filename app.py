import os
import re
import imaplib
import email
import time
import threading
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from email.header import decode_header

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
