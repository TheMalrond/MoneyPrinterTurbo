"""
Tradução automática dos termos de busca visual (PT → EN).

A busca de B-roll no Pexels/Pixabay funciona muito melhor com termos em
inglês (é o idioma majoritário do acervo e das tags). Este módulo permite
que quem usa o Clippa escreva os temas visuais em português, traduzindo
antes de repassar para a busca — sem exigir nenhuma chave de LLM.

MyMemory é a fonte principal (testada e estável neste ambiente); o
GoogleTranslator do deep-translator entra só como segunda tentativa. Se
ambas falharem (rede fora, cota estourada), a falha nunca deve derrubar a
geração do vídeo: devolvemos o texto original e a busca segue em
português mesmo, com resultados piores, mas o vídeo continua sendo gerado.
"""

import os

from loguru import logger

_MYMEMORY_EMAIL = os.getenv("MYMEMORY_EMAIL")

# MyMemory e Google, quando a chamada falha do lado deles (idioma inválido,
# página de erro do provedor etc.), às vezes devolvem HTTP 200 com uma
# mensagem de erro NO CORPO em vez de levantar exceção — o deep-translator
# repassa esse texto como se fosse a tradução. Um termo de busca de verdade
# é uma frase curta; qualquer coisa muito mais longa que o original, ou que
# bata com os padrões abaixo, é tratada como falha.
_ERROR_MARKERS = ("INVALID SOURCE LANGUAGE", "SERVER ERROR", "NO CONTENT")


def _looks_like_error(original: str, translated: str) -> bool:
    upper = translated.upper()
    if any(marker in upper for marker in _ERROR_MARKERS):
        return True
    return len(translated) > max(120, len(original) * 4)


def _translate_one(text: str) -> str:
    text = text.strip()
    if not text:
        return text

    try:
        from deep_translator import MyMemoryTranslator

        kwargs = {"email": _MYMEMORY_EMAIL} if _MYMEMORY_EMAIL else {}
        # MyMemory rejeita source="auto" (exige um idioma de origem explícito),
        # diferente do Google — por isso fixo pt-BR aqui, já que esta função
        # existe justamente para o caso de uso "termos escritos em português".
        translated = MyMemoryTranslator(
            source="pt-BR", target="en-GB", **kwargs
        ).translate(text)
        if translated and not _looks_like_error(text, translated):
            return translated.strip()
        if translated:
            logger.warning(f"MyMemory returned an error payload for {text!r}: {translated!r}")
    except Exception as e:
        logger.warning(f"MyMemory translation failed for {text!r}: {e}")

    try:
        from deep_translator import GoogleTranslator

        translated = GoogleTranslator(source="auto", target="en").translate(text)
        if translated and not _looks_like_error(text, translated):
            return translated.strip()
        if translated:
            logger.warning(f"Google returned an error payload for {text!r}: {translated!r}")
    except Exception as e:
        logger.warning(f"Google translation fallback failed for {text!r}: {e}")

    logger.warning(f"translation unavailable, using original text: {text!r}")
    return text


def translate_terms_to_english(terms: list[str]) -> list[str]:
    """Traduz cada termo independentemente (preserva a granularidade da lista)."""
    return [_translate_one(term) for term in terms]
