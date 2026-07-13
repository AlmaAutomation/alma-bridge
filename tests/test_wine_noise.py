from __future__ import annotations

from alma_bridge.execution.errors import format_wine_log_for_display, is_benign_wine_installer_stderr

SAMPLE = """0054:err:ole:StdMarshalImpl_MarshalInterface Failed to create ifstub, hr 0x80004002
0054:err:ole:start_rpcss Failed to open RpcSs service
wine: configuration in L"/home/joshua/.local/share/alma-bridge/prefixes/x" has been updated.
03ac:err:d3d:wined3d_context_gl_set_pixel_format wglSetPixelFormatWINE failed
"""


def test_benign_installer_stderr_detected():
    assert is_benign_wine_installer_stderr(SAMPLE)


def test_success_display_collapses_noise():
    text = format_wine_log_for_display(SAMPLE, success=True)
    assert "normal Wine noise" in text
    assert "not a failed install" in text
