# Busca imagens de produto reais na pasta pública do Google Drive que o time de
# marketing da Ybera já mantém como banco oficial de imagens (ver
# ~/.claude/skills/dev-mode-ecomm-on/cache/brand-assets.md). É uma pasta pública
# compartilhada por link, sem autenticação — não é o Drive pessoal de ninguém
# (isso é uma fonte de imagem separada, planejada pra depois de existir login).

import os
import random
import re
import unicodedata
from typing import List, Optional, Tuple

import requests
from loguru import logger

from app.config import config
from app.utils import utils

# "Produtos" dentro da pasta raiz "Drives" — uma subpasta por linha de produto
# (ex.: "1. Fashion Gold 1Kg" ... "40. Spa Pet"), packshots direto dentro de cada
# uma. Ver brand-assets.md para o resto do banco (institucional, MKT, etc.) — só
# "Produtos" interessa aqui.
PRODUTOS_FOLDER_ID = "1CxovSp5jBhXtC5nihPsx0S5cD87k0pYc"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

_ENTRY_ID_RE = re.compile(r'id="entry-([^"]+)"')
_ENTRY_NAME_RE = re.compile(r'flip-entry-title">([^<]+)')

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

_LEADING_NUMBER_RE = re.compile(r"^\d+\.\s*")
_SIZE_SUFFIX_RE = re.compile(r"\b\d+([.,]\d+)?\s*(kg|g|ml|l)\b", re.IGNORECASE)
_UNSAFE_FILENAME_RE = re.compile(r"[^\w.\-]")

# Nome de linha de produto normalizado precisa ter pelo menos esse tamanho pra
# contar como match — evita algo como "spa" batendo em qualquer texto por acaso.
_MIN_MATCH_LENGTH = 4


def _get_tls_verify() -> bool:
    # Mesmo padrão de app/services/material.py::_get_tls_verify — replicado aqui
    # (não importado) pra manter este módulo com dependências próprias e simples.
    tls_verify = config.app.get("tls_verify", True)
    if isinstance(tls_verify, str):
        tls_verify = tls_verify.strip().lower() not in ("0", "false", "no", "off")
    return bool(tls_verify)


def _list_drive_folder(folder_id: str) -> List[Tuple[str, str]]:
    """Lista (file_id, nome) dos itens de uma pasta pública do Drive, sem login."""
    url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#grid"
    response = requests.get(
        url,
        headers=_HEADERS,
        proxies=config.proxy,
        verify=_get_tls_verify(),
        timeout=(30, 60),
    )
    status_code = int(getattr(response, "status_code", 200))
    if status_code >= 400:
        raise ValueError(f"Drive folder listing failed: status={status_code}")

    ids = _ENTRY_ID_RE.findall(response.text)
    names = [name.strip() for name in _ENTRY_NAME_RE.findall(response.text)]
    if not ids or len(ids) != len(names):
        raise ValueError(f"unexpected Drive folder listing shape for {folder_id}")
    return list(zip(ids, names))


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = _LEADING_NUMBER_RE.sub("", text)
    text = _SIZE_SUFFIX_RE.sub("", text)
    return text.strip()


def _find_best_match(
    subfolders: List[Tuple[str, str]], search_text: str
) -> Optional[Tuple[str, str]]:
    """Escolhe a subpasta cujo nome normalizado é a MAIOR substring encontrada
    no texto de busca — evita que uma palavra curta genérica (ex.: "spa") dê
    match por acidente em qualquer roteiro."""
    normalized_search = _normalize(search_text)
    if not normalized_search:
        return None

    best = None
    best_len = 0
    for file_id, name in subfolders:
        candidate = _normalize(name)
        if len(candidate) < _MIN_MATCH_LENGTH:
            continue
        if candidate in normalized_search and len(candidate) > best_len:
            best = (file_id, name)
            best_len = len(candidate)

    return best


def _download_image(file_id: str, dest_path: str) -> bool:
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(
        url,
        headers=_HEADERS,
        proxies=config.proxy,
        verify=_get_tls_verify(),
        timeout=(60, 240),
    )
    status_code = int(getattr(response, "status_code", 200))
    if status_code >= 400:
        raise ValueError(f"Drive image download failed: status={status_code}")

    content_type = response.headers.get("Content-Type", "")
    if not content_type.startswith("image/"):
        # Drive às vezes devolve uma página de aviso/quota em vez do arquivo —
        # nunca gravar isso como se fosse imagem.
        logger.warning(
            f"ybera_bank: non-image response for file_id={file_id}, "
            f"content_type={content_type!r}"
        )
        return False

    with open(dest_path, "wb") as f:
        f.write(response.content)
    return True


def get_materials(
    task_id: str,
    search_text: str,
    needed_count: int = 15,
) -> Optional[List[str]]:
    """
    Busca fotos de produto Ybera reais pra usar como material do vídeo, a partir
    do texto combinado do roteiro + temas visuais (search_text).

    Devolve caminhos relativos a storage/local_videos/ (prontos pra virar
    MaterialInfo.url e passar por video.preprocess_video), ou None se não achou
    produto correspondente ou algo deu errado. NUNCA levanta exceção — quem chama
    deve cair pro Pexels quando o retorno for None, sem travar a geração do vídeo.
    """
    try:
        subfolders = _list_drive_folder(PRODUTOS_FOLDER_ID)

        match = _find_best_match(subfolders, search_text)
        if not match:
            logger.info("ybera_bank: no product folder matched the script/terms")
            return None

        folder_id, folder_name = match
        logger.info(f"ybera_bank: matched product folder '{folder_name}'")

        items = _list_drive_folder(folder_id)
        image_items = [
            (fid, name) for fid, name in items if name.lower().endswith(_IMAGE_EXTENSIONS)
        ]

        if not image_items:
            # Algumas linhas de produto guardam os packshots uma subpasta mais
            # fundo (ex.: uma subpasta por variante de tamanho, "300g"/"500g"),
            # em vez de direto na pasta da linha. O embeddedfolderview não
            # diferencia pasta de arquivo na listagem, então tentamos listar
            # cada item não-imagem como se fosse pasta e ignoramos em silêncio
            # quem não for (arquivos .docx/.pdf soltos, por exemplo).
            for sub_id, sub_name in items:
                if sub_name.lower().endswith(_IMAGE_EXTENSIONS):
                    continue
                try:
                    nested_items = _list_drive_folder(sub_id)
                except Exception:
                    continue
                image_items.extend(
                    (fid, name)
                    for fid, name in nested_items
                    if name.lower().endswith(_IMAGE_EXTENSIONS)
                )

        if not image_items:
            logger.warning(f"ybera_bank: no images found in folder '{folder_name}'")
            return None

        sample_size = min(needed_count, len(image_items))
        chosen = random.sample(image_items, sample_size)

        dest_dir = os.path.join(
            utils.storage_dir("local_videos", create=True), "ybera_bank", task_id
        )
        os.makedirs(dest_dir, exist_ok=True)

        relative_paths = []
        for file_id, name in chosen:
            safe_name = _UNSAFE_FILENAME_RE.sub("_", name)
            file_name = f"{file_id}_{safe_name}"
            dest_path = os.path.join(dest_dir, file_name)
            try:
                if _download_image(file_id, dest_path):
                    relative_paths.append(os.path.join("ybera_bank", task_id, file_name))
            except Exception as e:
                logger.warning(
                    f"ybera_bank: failed to download image {file_id} ({name}): {str(e)}"
                )

        if not relative_paths:
            logger.warning(
                f"ybera_bank: matched folder '{folder_name}' but no image could be downloaded"
            )
            return None

        logger.success(
            f"ybera_bank: downloaded {len(relative_paths)} image(s) from '{folder_name}'"
        )
        return relative_paths
    except Exception as e:
        logger.warning(f"ybera_bank: failed, falling back to Pexels, error: {str(e)}")
        return None
