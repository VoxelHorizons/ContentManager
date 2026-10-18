"""Display smoke: Windows CI executes; headless Linux explicitly skips."""
import os
import sys
import time
import pytest

from test_content_manager import fixture_pack


@pytest.mark.skipif(sys.platform != 'win32' and not os.environ.get('DISPLAY'), reason='Tk requires a display')
def test_workspace_generator_and_resolved_preview(tmp_path, monkeypatch):
    from content_manager.app import ContentManagerApp
    from tkinter import messagebox
    errors = []
    monkeypatch.setattr(messagebox, 'showerror', lambda title, text: errors.append(text))
    pack, source = fixture_pack(tmp_path)
    app = ContentManagerApp()
    app.withdraw()
    def finish():
        deadline = time.monotonic() + 10
        while app._busy and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert not app._busy
        assert not errors
    try:
        app._open(str(pack))
        finish()
        assert app.workspace.items[source]
        node = next(node for node, ident in app.tree_items.items() if ident == source)
        app.tree.selection_set(node)
        app._on_tree_select()
        assert app.preview.model['elements']
        app._plan()
        finish()
        assert app.current_plan.changed
        app.texture_slot.set('missing')
        assert app.current_plan is None
        assert str(app.apply_button['state']) == 'disabled'
    finally:
        app.destroy()
