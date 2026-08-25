import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import config
from app.services import ybera_bank


def _folder_html(entries):
    # Reproduz o formato mínimo que o parser espera de
    # https://drive.google.com/embeddedfolderview?id=<ID>#grid:
    # pares id="entry-<ID>" / flip-entry-title">Nome<
    parts = []
    for file_id, name in entries:
        parts.append(f'<div id="entry-{file_id}" class="flip-entry">')
        parts.append(f'<div class="flip-entry-title">{name}</div>')
    return "\n".join(parts)


class TestYberaBank(unittest.TestCase):
    def setUp(self):
        self.original_app_config = dict(config.app)
        self.original_proxy_config = dict(config.proxy)
        self.tmp_dir = tempfile.mkdtemp()
        self._patch_storage = patch(
            "app.services.ybera_bank.utils.storage_dir", return_value=self.tmp_dir
        )
        self._patch_storage.start()

    def tearDown(self):
        self._patch_storage.stop()
        config.app.clear()
        config.app.update(self.original_app_config)
        config.proxy.clear()
        config.proxy.update(self.original_proxy_config)

    def test_find_best_match_picks_longest_folder_name(self):
        subfolders = [
            ("id1", "1. Fashion Gold 1Kg"),
            ("id2", "40. Spa Pet"),
            ("id3", "Combos"),
        ]
        search_text = (
            "Voce tem medo de fazer progressiva, por causa do formol? Que tal "
            "experimentar a progressiva Fashion Gold hoje? Acesse agora mesmo: "
            "ybera.com"
        )
        match = ybera_bank._find_best_match(subfolders, search_text)
        self.assertEqual(match, ("id1", "1. Fashion Gold 1Kg"))

    def test_find_best_match_rejects_short_generic_words(self):
        # "spa" sozinho não pode bater com qualquer texto que contenha a
        # palavra por acaso — evita falso-positivo de pasta genérica.
        subfolders = [("id1", "Spa")]
        match = ybera_bank._find_best_match(subfolders, "um dia de spa em casa")
        self.assertIsNone(match)

    def test_find_best_match_returns_none_without_product_mention(self):
        subfolders = [("id1", "1. Fashion Gold 1Kg"), ("id2", "40. Spa Pet")]
        match = ybera_bank._find_best_match(
            subfolders, "um roteiro qualquer sem nenhum produto mencionado"
        )
        self.assertIsNone(match)

    def test_get_materials_downloads_matched_product_images(self):
        root_html = _folder_html([("root-id", "1. Fashion Gold 1Kg")])
        product_html = _folder_html(
            [("img1", "packshot-1.jpg"), ("img2", "packshot-2.jpg")]
        )
        image_bytes = b"\xff\xd8\xff fake jpeg bytes"

        responses = [
            SimpleNamespace(status_code=200, text=root_html),
            SimpleNamespace(status_code=200, text=product_html),
            SimpleNamespace(
                status_code=200,
                headers={"Content-Type": "image/jpeg"},
                content=image_bytes,
            ),
            SimpleNamespace(
                status_code=200,
                headers={"Content-Type": "image/jpeg"},
                content=image_bytes,
            ),
        ]

        with patch(
            "app.services.ybera_bank.requests.get", side_effect=responses
        ) as get:
            result = ybera_bank.get_materials(
                task_id="task-1",
                search_text="progressiva Fashion Gold hoje, acesse ybera.com",
                needed_count=2,
            )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        for relative_path in result:
            self.assertTrue(relative_path.startswith(os.path.join("ybera_bank", "task-1")))
            full_path = os.path.join(self.tmp_dir, relative_path)
            self.assertTrue(os.path.isfile(full_path))
        self.assertEqual(get.call_count, 4)

    def test_get_materials_recurses_into_size_variant_subfolders(self):
        # Descoberto em teste manual real: algumas linhas de produto (ex.:
        # "Progressiva Fashion Gold") não têm packshot direto na pasta da
        # linha — têm uma subpasta por variante de tamanho (300g/500g), com
        # os packshots (e às vezes um .docx solto) dentro de cada variante.
        root_html = _folder_html([("root-id", "2. Progressiva Fashion Gold")])
        line_html = _folder_html(
            [
                ("variant-300g", "1. Progressiva Fashion Gold 300g"),
                ("doc-id", "Progressiva Fashion Gold - 300g.docx"),
            ]
        )
        variant_html = _folder_html([("img1", "300g-beneficios.jpg")])
        doc_response = SimpleNamespace(status_code=200, text="")  # não é pasta
        image_bytes = b"\xff\xd8\xff fake jpeg bytes"

        responses = [
            SimpleNamespace(status_code=200, text=root_html),  # raiz Produtos
            SimpleNamespace(status_code=200, text=line_html),  # pasta da linha
            SimpleNamespace(status_code=200, text=variant_html),  # subpasta 300g
            doc_response,  # tentativa de listar o .docx como pasta -> falha
            SimpleNamespace(
                status_code=200,
                headers={"Content-Type": "image/jpeg"},
                content=image_bytes,
            ),
        ]

        with patch("app.services.ybera_bank.requests.get", side_effect=responses):
            result = ybera_bank.get_materials(
                task_id="task-nested",
                search_text="a progressiva fashion gold 300g e otima",
                needed_count=5,
            )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertTrue(
            os.path.isfile(os.path.join(self.tmp_dir, result[0]))
        )

    def test_get_materials_returns_none_without_match(self):
        root_html = _folder_html([("root-id", "40. Spa Pet")])
        fake_response = SimpleNamespace(status_code=200, text=root_html)

        with patch(
            "app.services.ybera_bank.requests.get", return_value=fake_response
        ):
            result = ybera_bank.get_materials(
                task_id="task-2",
                search_text="um roteiro qualquer sem nenhum produto mencionado",
            )

        self.assertIsNone(result)

    def test_get_materials_never_raises_on_network_failure(self):
        with patch(
            "app.services.ybera_bank.requests.get",
            side_effect=ConnectionError("network unreachable"),
        ):
            result = ybera_bank.get_materials(
                task_id="task-3",
                search_text="progressiva Fashion Gold",
            )

        self.assertIsNone(result)

    def test_get_materials_rejects_non_image_download(self):
        root_html = _folder_html([("root-id", "1. Fashion Gold 1Kg")])
        product_html = _folder_html([("img1", "packshot-1.jpg")])
        error_page = SimpleNamespace(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>quota exceeded</html>",
        )

        responses = [
            SimpleNamespace(status_code=200, text=root_html),
            SimpleNamespace(status_code=200, text=product_html),
            error_page,
        ]

        with patch("app.services.ybera_bank.requests.get", side_effect=responses):
            result = ybera_bank.get_materials(
                task_id="task-4",
                search_text="progressiva Fashion Gold",
            )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
