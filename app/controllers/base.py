from uuid import uuid4

from fastapi import Request

from app.config import config
from app.models.exception import HttpException


def get_task_id(request: Request):
    task_id = request.headers.get("x-task-id")
    if not task_id:
        task_id = uuid4()
    return str(task_id)


def get_api_key(request: Request):
    api_key = request.headers.get("x-api-key")
    return api_key


def verify_token(request: Request):
    expected_token = config.app.get("api_key", "")
    if not expected_token:
        # Nenhuma api_key configurada: autenticação fica desligada (uso local/dev).
        # Só passa a exigir x-api-key quando o operador define uma chave real,
        # o que é obrigatório antes de expor a API na internet (ex.: Render).
        return
    token = get_api_key(request)
    if token != expected_token:
        request_id = get_task_id(request)
        request_url = request.url
        user_agent = request.headers.get("user-agent")
        raise HttpException(
            task_id=request_id,
            status_code=401,
            message=f"invalid token: {request_url}, {user_agent}",
        )
