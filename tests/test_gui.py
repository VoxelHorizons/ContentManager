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
        # Real Java execution is tested separately by pinned JDK25 CI.
        # Tkinter must invoke the same service on a worker and report its result.
        from content_manager import validation
        from content_manager.validation import JavaValidationResult
        def fake_java(ws, cp, target, allocations):
            assert ws is app.workspace
            assert cp == "compiler-classpath.txt"
            assert target == "mc-26.3"
            assert allocations is None
            return JavaValidationResult(True, target, 3, "0" * 64,
                                        1, 0, 1, "VOXELCORE_VALIDATION_OK", "", 0)
        monkeypatch.setattr(validation, "validate_java", fake_java)
        app.java_classpath.set("compiler-classpath.txt")
        app._validate_java()
        finish()
        assert "Java validation: PASSED" in app.diagnostics_text.get("1.0", "end")
        assert not app._busy
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
        app.edit_name.set('&aUpdated Table')
        app._fields_to_yaml()
        app._preview_edit()
        finish()
        assert app.edit_plan.changed
        assert b'Updated Table' in app.edit_plan.outputs[0].payload
    finally:
        app.destroy()
