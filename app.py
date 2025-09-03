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

# Configurações do email e Kommo (via variáveis de ambiente)
EMAIL_CONFIG = {
    'server': os.getenv('EMAIL_SERVER', 'imap.gmail.com'),
    'port': int(os.getenv('EMAIL_PORT', 993)),
    'username': os.getenv('EMAIL_USERNAME'),
    'password': os.getenv('EMAIL_PASSWORD')
}

KOMMO_CONFIG = {
    'subdomain': os.getenv('KOMMO_SUBDOMAIN'),
    'access_token': os.getenv('KOMMO_TOKEN')
}

# Monitor de email global
email_monitor = None
monitoring_active = False

def extract_olx_data(content, sender):
    """Extrai dados de emails da OLX"""
    data = {
        'portal': 'OLX',
        'source': sender,
        'name': '',
        'phone': '',
        'email': '',
        'vehicle_interest': '',
        'whatsapp': ''
    }
    
    # Extrair nome
    name_match = re.search(r'Nome:\s*([^\n\r]+)', content)
    if name_match:
        data['name'] = name_match.group(1).strip()
    
    # Extrair email
    email_match = re.search(r'Email:\s*([^\n\r]+)', content)
    if email_match:
        data['email'] = email_match.group(1).strip()
    
    # Extrair telefone
    phone_match = re.search(r'Telefone:\s*([^\n\r]+)', content)
    if phone_match:
        phone = phone_match.group(1).strip()
        data['phone'] = phone
        data['whatsapp'] = phone
    
    # Extrair veículo de interesse
    vehicle_match = re.search(r'([A-Z][A-Z\s]+\d+(?:\.\d+)?(?:\s+\d{4})?)', content)
    if vehicle_match:
        data['vehicle_interest'] = vehicle_match.group(1).strip()
    
    return data

def extract_socarrao_data(content, sender):
    """Extrai dados de emails do Só Carrão"""
    data = {
        'portal': 'Só Carrão',
        'source': sender,
        'name': '',
        'phone': '',
        'email': '',
        'vehicle_interest': '',
        'whatsapp': ''
    }
    
    # Extrair nome
    name_match = re.search(r'De:\s*([^\n\r]+)', content)
    if name_match:
        data['name'] = name_match.group(1).strip()
    
    # Extrair email
    email_match = re.search(r'Email:\s*([^\n\r]+)', content)
    if email_match:
        data['email'] = email_match.group(1).strip()
    
    # Extrair telefone
    phone_match = re.search(r'Telefone:\s*([^\n\r]+)', content)
    if phone_match:
        phone = phone_match.group(1).strip()
        data['phone'] = phone
        data['whatsapp'] = phone
    
    return data

def extract_icarros_data(content, sender):
    """Extrai dados de emails do iCarros"""
    data = {
        'portal': 'iCarros',
        'source': sender,
        'name': '',
        'phone': '',
        'email': '',
        'vehicle_interest': '',
        'whatsapp': ''
    }
    
    # Extrair nome
    name_match = re.search(r'Nome\s+([^\n\r]+)', content)
    if name_match:
        data['name'] = name_match.group(1).strip()
    
    # Extrair email
    email_match = re.search(r'E-mail\s+([^\n\r]+)', content)
    if email_match:
        data['email'] = email_match.group(1).strip()
    
    # Extrair telefone
    phone_match = re.search(r'Telefone\s+([^\n\r]+)', content)
    if phone_match:
        phone = phone_match.group(1).strip()
        data['phone'] = phone
        data['whatsapp'] = phone
    
    return data

def send_to_kommo(lead_data):
    """Envia lead para o Kommo CRM"""
    try:
        if not KOMMO_CONFIG['subdomain'] or not KOMMO_CONFIG['access_token']:
            return {'success': False, 'error': 'Configurações do Kommo não encontradas'}
        
        # URL da API do Kommo
        url = f"https://{KOMMO_CONFIG['subdomain']}.kommo.com/api/v4/leads"
        
        # Limpar o token (remover espaços e quebras de linha )
        clean_token = KOMMO_CONFIG['access_token'].strip()
        
        headers = {
            'Authorization': f"Bearer {clean_token}",
            'Content-Type': 'application/json'
        }
        
        # Preparar dados do lead
        lead_payload = {
            'name': f"Lead {lead_data['portal']} - {lead_data['name']}",
            'price': 0,
            '_embedded': {
                'contacts': [{
                    'name': lead_data['name'],
                    'custom_fields_values': []
                }]
            }
        }
        
        # Adicionar telefone ao contato se disponível
        if lead_data['phone']:
            lead_payload['_embedded']['contacts'][0]['custom_fields_values'].append({
                'field_code': 'PHONE',
                'values': [{'value': lead_data['phone'], 'enum_code': 'WORK'}]
            })
        
        # Adicionar email ao contato se disponível
        if lead_data['email']:
            lead_payload['_embedded']['contacts'][0]['custom_fields_values'].append({
                'field_code': 'EMAIL',
                'values': [{'value': lead_data['email'], 'enum_code': 'WORK'}]
            })
        
        # Fazer requisição para criar lead
        response = requests.post(url, json=[lead_payload], headers=headers, timeout=30)
        
        if response.status_code == 200:
            lead_response = response.json()
            lead_id = lead_response['_embedded']['leads'][0]['id']
            
            # Adicionar nota ao lead
            notes_url = f"https://{KOMMO_CONFIG['subdomain']}.kommo.com/api/v4/leads/{lead_id}/notes"
            notes = []
            notes.append(f"🚗 Portal: {lead_data['portal']}" )
            if lead_data['vehicle_interest']:
                notes.append(f"🚙 Veículo: {lead_data['vehicle_interest']}")
            if lead_data['whatsapp']:
                notes.append(f"📱 WhatsApp: {lead_data['whatsapp']}")
            
            note_payload = [{
                'note_type': 'common',
                'params': {
                    'text': '\n'.join(notes)
                }
            }]
            
            requests.post(notes_url, json=note_payload, headers=headers, timeout=30)
            
            return {
                'success': True,
                'lead_id': lead_id,
                'message': 'Lead criado com sucesso no Kommo'
            }
        else:
            return {
                'success': False,
                'error': f'Erro na API do Kommo: {response.status_code} - {response.text}'
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': f'Erro ao enviar para Kommo: {str(e)}'
        }

def process_email_content(sender, subject, content):
    """Processa conteúdo do email e extrai dados do lead"""
    try:
        sender_lower = sender.lower()
        
        if 'olx.com.br' in sender_lower:
            return extract_olx_data(content, sender)
        elif 'socarrao.com.br' in sender_lower:
            return extract_socarrao_data(content, sender)
        elif 'icarros.com.br' in sender_lower:
            return extract_icarros_data(content, sender)
        elif 'webmotors.com.br' in sender_lower:
            data = extract_icarros_data(content, sender)
            data['portal'] = 'Webmotors'
            return data
        elif 'mobiauto.com.br' in sender_lower:
            data = extract_icarros_data(content, sender)
            data['portal'] = 'Mobi Auto'
            return data
        elif 'napista.com.br' in sender_lower:
            data = extract_icarros_data(content, sender)
            data['portal'] = 'Na Pista'
            return data
        else:
            return {
                'portal': 'Desconhecido',
                'source': sender,
                'name': '',
                'phone': '',
                'email': '',
                'vehicle_interest': subject,
                'whatsapp': ''
            }
    except Exception as e:
        logger.error(f"Erro ao processar email: {str(e)}")
        return None

# Rotas da API
@app.route('/')
def home():
    return jsonify({
        'message': 'Sistema de Automação de Leads - Euro Car Seminovos',
        'status': 'online',
        'endpoints': {
            'health': '/health',
            'test': '/test',
            'webhook_kommo': '/webhook/kommo',
            'webhook_email': '/webhook/email',
            'manual_lead': '/manual-lead'
        }
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.route('/test')
def test():
    # Testar com dados de exemplo da OLX
    sample_content = """
    Oi, Eurocar!

    Você recebeu um novo interessado em comprar o seu veículo:

    FIAT UNO ATTRACTIVE 1.0 2020
    R$ 42900,00

    Nome: Wesley Pablo
    Email: wesleypabloecia@gmail.com
    Telefone: 43999155017
    """
    
    lead_data = extract_olx_data(sample_content, "noreply@olx.com.br")
    kommo_result = send_to_kommo(lead_data)
    
    return jsonify({
        'test_data': lead_data,
        'kommo_result': kommo_result,
        'status': 'test_completed'
    })

@app.route('/webhook/kommo', methods=['POST'])
def kommo_webhook():
    """Recebe webhooks do Kommo"""
    try:
        data = request.get_json()
        logger.info(f"Webhook recebido do Kommo: {data}")
        
        # Log para debug
        return jsonify({
            'status': 'received',
            'message': 'Webhook processado com sucesso',
            'data': data
        }), 200
        
    except Exception as e:
        logger.error(f"Erro no webhook do Kommo: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/webhook/email', methods=['POST'])
def email_webhook():
    """Processa emails e cria leads no Kommo"""
    try:
        data = request.get_json()
        
        # Extrair dados do email
        sender = data.get('sender', '')
        subject = data.get('subject', '')
        content = data.get('content', '')
        
        # Processar conteúdo do email
        lead_data = process_email_content(sender, subject, content)
        
        if lead_data:
            # Tentar enviar para Kommo
            kommo_result = send_to_kommo(lead_data)
            
            return jsonify({
                'status': 'success',
                'lead_data': lead_data,
                'kommo_result': kommo_result
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Não foi possível processar o email'
            }), 400
            
    except Exception as e:
        logger.error(f"Erro no webhook de email: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/manual-lead', methods=['POST'])
def create_manual_lead():
    """Cria lead manualmente para teste"""
    try:
        # Dados de exemplo para teste
        lead_data = {
            'portal': 'Teste Manual',
            'source': 'teste@exemplo.com',
            'name': 'Cliente Teste',
            'phone': '11999999999',
            'email': 'cliente@teste.com',
            'vehicle_interest': 'Carro de Teste',
            'whatsapp': '11999999999'
        }
        
        # Enviar para Kommo
        kommo_result = send_to_kommo(lead_data)
        
        return jsonify({
            'status': 'success',
            'message': 'Lead de teste criado',
            'lead_data': lead_data,
            'kommo_result': kommo_result
        }), 200
        
    except Exception as e:
        logger.error(f"Erro ao criar lead manual: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
