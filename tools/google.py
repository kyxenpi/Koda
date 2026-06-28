import json
import datetime
import io
import ast 
from pathlib import Path
from typing import Any, Dict
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

from tools.base import tool
from config import settings
from core.security import SecurityLevel
from core.logger import setup_logger
from database.memory_db import db

logger = setup_logger("GoogleTools")

def safe_parse_args(args: Any) -> Dict[str, Any]:
    """Garante que os argumentos sejam convertidos em um dicionário válido, 
    mesmo se o LLM enviar uma string ou usar aspas simples."""
    if isinstance(args, dict):
        return args
    
    if isinstance(args, str):
        args_str = args.strip()
        # Tenta parsear como JSON padrão
        try:
            return json.loads(args_str)
        except json.JSONDecodeError:
            # Se falhar (ex: uso de aspas simples pelo modelo), usa ast.literal_eval
            try:
                parsed = ast.literal_eval(args_str)
                if isinstance(parsed, dict):
                    return parsed
            except Exception as e:
                logger.error(f"Falha ao normalizar argumentos textuais: {e}")
    
    return {}

def get_google_credentials():
    creds = None
    token_path = Path('token.json')
    
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), settings.SCOPES)
    elif settings.GOOGLE_TOKEN_JSON:
        try:
            creds = Credentials.from_authorized_user_info(json.loads(settings.GOOGLE_TOKEN_JSON), settings.SCOPES)
        except Exception as e:
            logger.error(f"Erro parse GOOGLE_TOKEN_JSON: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as refresh_error:
                logger.warning(f"Não foi possível atualizar o token expirado: {refresh_error}")
                if "invalid_grant" in str(refresh_error) and token_path.exists():
                    token_path.unlink()
                creds = None

        if not creds:
            if Path('credentials.json').exists():
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', settings.SCOPES)
                creds = flow.run_local_server(port=0)
            elif settings.GOOGLE_CREDENTIALS_JSON:
                flow = InstalledAppFlow.from_client_config(json.loads(settings.GOOGLE_CREDENTIALS_JSON), settings.SCOPES)
                creds = flow.run_local_server(port=0)
            else:
                raise Exception("Credenciais nulas e impossível autenticar.")
                
            if not settings.GOOGLE_TOKEN_JSON:
                token_path.write_text(creds.to_json())
                    
    return creds

@tool("google_docs", security_level=SecurityLevel.MEDIUM, cloud_compatible=True)
def google_docs_tool(args: Any) -> Dict[str, Any]:
    """Cria ou edita documentos no Google Docs gerenciando IDs estruturalmente."""
    try:
        creds = get_google_credentials()
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Garante o parse correto dos argumentos
        args_dict = safe_parse_args(args)
        if not args_dict and isinstance(args, str):
            args_dict = {"title": f"Doc Koda - {datetime.date.today()}", "content": args}

        doc_id = args_dict.get("document_id") or args_dict.get("documentId") or args_dict.get("documentid") or args_dict.get("file_id") or args_dict.get("id")
        content = args_dict.get("content") or args_dict.get("text") or args_dict.get("body") or ""

        if doc_id:
            try:
                export_request = drive_service.files().export_media(fileId=doc_id, mimeType='text/html')
                html_atual = export_request.execute().decode('utf-8')
                corpo_antigo = html_atual.split("<body>")[1].split("</body>")[0] if "<body>" in html_atual else html_atual
            except:
                corpo_antigo = ""

            conteudo_limpo = corpo_antigo.replace("<p>", "").replace("</p>", "").replace("<br>", "\n")
            linhas_filtradas = [l for l in content.split('\n') if l.strip() and l.strip() not in conteudo_limpo]

            if not linhas_filtradas:
                return {
                    "success": True,
                    "result": {
                        "document_id": doc_id,
                        "status": "Duplicidade evitada."
                    }
                }
                
            novo_html = "\n".join(linhas_filtradas).replace('\n', '<br>')
            html_final = f"<html><body>{corpo_antigo}<br><br>{novo_html}</body></html>" if corpo_antigo.strip() else f"<html><body>{novo_html}</body></html>"

            fh = io.BytesIO(html_final.encode('utf-8'))
            media = MediaIoBaseUpload(fh, mimetype='text/html', resumable=True)
            drive_service.files().update(fileId=doc_id, media_body=media).execute()
            return {"success": True, "result": {"document_id": doc_id, "status": "Doc atualizado."}}

        title = args_dict.get("title", f"Doc Koda - {datetime.date.today()}")
        file_metadata = {'name': title, 'mimeType': 'application/vnd.google-apps.document'}
        texto_formatado = content.replace('\n', '<br>')
        content_html = f"<html><body>{texto_formatado}</body></html>"
        
        fh = io.BytesIO(content_html.encode('utf-8'))
        media = MediaIoBaseUpload(fh, mimetype='text/html', resumable=True)
        doc_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        
        new_id = doc_file.get('id')
        db.save_metadata("last_google_doc_id", new_id)
        return {"success": True, "result": {"document_id": new_id, "status": "Criado com sucesso."}}
    except Exception as e:
        return {"success": False, "error": str(e)}

@tool("upload_to_drive", security_level=SecurityLevel.MEDIUM)
def upload_to_drive(args: Any) -> str:
    """Envia um arquivo local para o Google Drive."""
    local_path = args.get("local_path") if isinstance(args, dict) else args
    drive_name = args.get("drive_name") if isinstance(args, dict) else Path(local_path).name
    
    if not Path(local_path).exists():
        return "Erro: Arquivo local inexistente."
        
    try:
        creds = get_google_credentials()
        service = build('drive', 'v3', credentials=creds)
        media = MediaFileUpload(local_path, resumable=True)
        file = service.files().create(body={'name': drive_name}, media_body=media, fields='id').execute()
        return f"Sucesso! ID: {file.get('id')}"
    except Exception as e:
        return f"Falha: {str(e)}"

# ==========================================
# FERRAMENTAS DO GOOGLE AGENDA (CALENDAR)
# ==========================================

@tool("google_calendar_add", security_level=SecurityLevel.SAFE, cloud_compatible=True)
def google_calendar_add(args: Any) -> Dict[str, Any]:
    """Adiciona um evento à agenda do Google. Requer 'summary', 'date' (YYYY-MM-DD) e 'time' (HH:MM). Opcional: 'description'."""
    try:
        creds = get_google_credentials()
        service = build('calendar', 'v3', credentials=creds)

        # Normaliza a entrada dos argumentos independente de vir como string errada ou dict
        args_dict = safe_parse_args(args)

        summary = args_dict.get("summary") or args_dict.get("title") or args_dict.get("description")
        date = args_dict.get("date")
        time_input = args_dict.get("time", "09:00")
        description = args_dict.get("description", "Adicionado pelo Koda")

        if not summary or not date:
            return {"success": False, "error": "Parâmetros 'summary' (ou 'title') e 'date' são obrigatórios."}

        # Tratamento caso o LLM mande a hora completa com segundos (ex: 00:00:00) -> Reduz para HH:MM
        if time_input and len(time_input.split(':')) >= 2:
            parts = time_input.split(':')
            time_input = f"{int(parts[0]):02d}:{int(parts[1]):02d}"

        start_datetime = f"{date}T{time_input}:00"
        
        try:
            dt_start = datetime.datetime.fromisoformat(start_datetime)
            dt_end = dt_start + datetime.timedelta(hours=1)
            end_datetime = dt_end.isoformat()
        except Exception:
            # Fallback seguro caso o cálculo falhe por strings corrompidas
            try:
                hora_adicional = int(time_input.split(':')[0]) + 1
                if hora_adicional >= 24:
                    end_datetime = f"{date}T23:59:59"
                else:
                    end_datetime = f"{date}T{hora_adicional:02d}:{time_input.split(':')[1]}:00"
            except:
                end_datetime = f"{date}T23:59:59"

        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_datetime,
                'timeZone': 'America/Sao_Paulo',
            },
            'end': {
                'dateTime': end_datetime,
                'timeZone': 'America/Sao_Paulo',
            },
        }

        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return {
            "success": True, 
            "result": {
                "event_id": created_event.get("id"), 
                "link": created_event.get("htmlLink"),
                "status": f"Evento '{summary}' agendado com sucesso!"
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("google_calendar_list", security_level=SecurityLevel.SAFE, cloud_compatible=True)
def google_calendar_list(args: Any = None) -> Dict[str, Any]:
    """Lista os próximos 10 compromissos da agenda do Google."""
    try:
        creds = get_google_credentials()
        service = build('calendar', 'v3', credentials=creds)

        now = datetime.datetime.utcnow().isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId='primary', 
            timeMin=now,
            maxResults=10, 
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])

        if not events:
            return {"success": True, "result": "Nenhum compromisso futuro encontrado."}

        formatted_events = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            clean_start = start.replace("T", " às ").split("-03")[0]
            formatted_events.append(f"- [{clean_start}] {event.get('summary')} (ID: {event.get('id')})")

        return {"success": True, "result": "\n".join(formatted_events)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("google_calendar_clear", security_level=SecurityLevel.MEDIUM, cloud_compatible=True)
def google_calendar_clear(args: Any = None) -> Dict[str, Any]:
    """Apaga os próximos compromissos da agenda (limpa os próximos 10 eventos encontrados)."""
    try:
        creds = get_google_credentials()
        service = build('calendar', 'v3', credentials=creds)

        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(calendarId='primary', timeMin=now, maxResults=10, singleEvents=True).execute()
        events = events_result.get('items', [])

        if not events:
            return {"success": True, "result": "A agenda já está limpa (nenhum evento futuro encontrado)."}

        deleted_count = 0
        for event in events:
            service.events().delete(calendarId='primary', eventId=event['id']).execute()
            deleted_count += 1

        return {"success": True, "result": f"Sucesso! Foram removidos os próximos {deleted_count} eventos da sua agenda."}
    except Exception as e:
        return {"success": False, "error": str(e)}