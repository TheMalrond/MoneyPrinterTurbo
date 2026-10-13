"""Fork Clippa: fontes próprias (Banco Ybera) passam no preflight do upstream."""

from unittest.mock import patch

import pytest

from app.models.schema import TaskVideoRequest
from app.services import task as tm
from app.services.state import MemoryState


@pytest.mark.parametrize("source", ["ybera_bank", "ybera_bank,pexels", "pexels"])
def test_ybera_sources_pass_preflight(source):
    params = TaskVideoRequest(
        video_subject="Fashion Gold", video_source=source, subtitle_enabled=False
    )
    state = MemoryState()
    with (
        patch.object(tm.sm, "state", state),
        patch.object(tm, "generate_script", return_value=None) as script,
    ):
        tm.start("task-1", params, stop_at="video")
    # Preflight aprovou: a execução chegou à etapa de roteiro.
    script.assert_called_once()


def test_combined_source_with_unknown_member_fails():
    params = TaskVideoRequest(
        video_subject="x", video_source="ybera_bank,pexel", subtitle_enabled=False
    )
    state = MemoryState()
    with patch.object(tm.sm, "state", state):
        result = tm.start("task-1", params, stop_at="video")
    assert result["failed_stage"] == "preflight"
