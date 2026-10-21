"""Voxel Horizons Content Manager — native Tkinter desktop interface."""
from __future__ import annotations
import json
import queue
import threading
import yaml
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .core import (COLORS, WOODS, SUPPORTED_TARGETS, ContentError, Plan,
                   Workspace, _palette, apply_plan, plan_family, plan_new_item)
from .preview import ModelPreview
from .assets import ModelResolver, ReferenceGraph
from .transactions import restore, pending_snapshots
from .editing import plan_edit_item, parse_item_text
from .recipes import plan_recipe
from .core import UniqueSafeLoader


class ContentManagerApp(tk.Tk):
    def __init__(self, root_path: str | None = None):
        super().__init__()
        self.title("Voxel Horizons • Content Manager")
        self.geometry("1380x850")
        self.minsize(1030, 700)
        self.configure(background="#121d28")
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", background="#182634", foreground="#e8edf5", fieldbackground="#223343", font=("Segoe UI", 10))
        style.configure("TFrame", background="#182634")
        style.configure("TLabel", background="#182634", foreground="#e8edf5")
        style.configure("Heading.TLabel", font=("Segoe UI Semibold", 13), foreground="#f6f8fa")
        style.configure("Sub.TLabel", foreground="#97a9be")
        style.configure("TButton", padding=(9, 5), background="#30495e", foreground="#f6f8fa")
        style.configure("Accent.TButton", padding=(12, 7), background="#237d97", foreground="#ffffff")
        style.configure("TEntry", fieldbackground="#223343", foreground="#ffffff")
        style.configure("TCombobox", fieldbackground="#223343", foreground="#ffffff")
        style.configure("TNotebook", background="#172634")
        style.configure("TNotebook.Tab", padding=(14, 8), background="#30465a", foreground="#e6ecf2")
        style.map("TNotebook.Tab", background=[("selected", "#237d97")])
        style.configure("Treeview", background="#1b2b39", foreground="#e8edf5", fieldbackground="#1b2b39", rowheight=25)
        style.map("Treeview", background=[("selected", "#237d97")])
        self._busy = False
        self._results = queue.Queue()
        self.graph = None
        self.recipe_plan = None
        self.edit_plan = None
        self.edit_dirty = False
        self._loading_editor = False
        self.editor_id = None
        self._fields_pending = False
        self.edit_name = tk.StringVar()
        self.edit_material = tk.StringVar()
        self.edit_model = tk.StringVar()
        self.edit_abstract = tk.StringVar(value="inherit")
        self.workspace: Workspace | None = None
        self.current_id: str | None = None
        self.current_plan: Plan | None = None
        self.new_plan: Plan | None = None
        self.new_namespace = tk.StringVar()
        self.new_name = tk.StringVar()
        self.new_label = tk.StringVar()
        self.new_kind = tk.StringVar(value="furniture")
        self.new_material = tk.StringVar(value="minecraft:paper")
        self.new_model = tk.StringVar()
        self.tree_items: dict[str, str] = {}
        self.path = tk.StringVar(value="No workspace loaded")
        self.search = tk.StringVar()
        self.family = tk.StringVar(value="wood")
        self.target = tk.StringVar(value="mc-26.3")
        # Operator-supplied compiler dependencies stay session-local.
        self.java_classpath = tk.StringVar()
        self.java_allocations = tk.StringVar()
        self.strategy = tk.StringVar(value="alias")
        self.texture_slot = tk.StringVar(value="")
        self.status = tk.StringVar(value="Select a VoxelCore content folder or an individual pack.")
        self.include_dependencies = tk.BooleanVar(value=False)
        self.show_diff = tk.BooleanVar(value=False)
        self._create_widgets()
        self.search.trace_add("write", lambda *_: self._build_tree())
        self.family.trace_add("write", lambda *_: self._load_palette())
        self.target.trace_add("write", lambda *_: self._load_palette())
        if root_path:
            self._open(root_path)

    def _create_widgets(self):
        header = ttk.Frame(self, padding=14)
        header.pack(fill="x")
        ttk.Label(header, text="VOXEL HORIZONS  /  CONTENT MANAGER", style="Heading.TLabel").pack(side="left")
        ttk.Button(header, text="Open workspace", command=self._choose_workspace).pack(side="right", padx=5)
        ttk.Button(header, text="Refresh", command=self._refresh).pack(side="right", padx=5)
        subtitle = ttk.Frame(self, padding=(15, 0, 15, 10))
        subtitle.pack(fill="x")
        ttk.Label(subtitle, textvariable=self.path, style="Sub.TLabel").pack(anchor="w")
        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=12)
        left = ttk.Frame(main, padding=10)
        right = ttk.Frame(main, padding=8)
        main.add(left, weight=1)
        main.add(right, weight=4)
        ttk.Label(left, text="Content explorer", style="Heading.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Entry(left, textvariable=self.search).pack(fill="x", pady=(0, 8))
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)
        inspect = ttk.Frame(notebook, padding=12)
        editor = ttk.Frame(notebook, padding=12)
        creator = ttk.Frame(notebook, padding=12)
        generator = ttk.Frame(notebook, padding=12)
        recipes = ttk.Frame(notebook, padding=12)
        assets = ttk.Frame(notebook, padding=12)
        diagnostics = ttk.Frame(notebook, padding=12)
        relationships = ttk.Frame(notebook, padding=12)
        recovery = ttk.Frame(notebook, padding=12)
        notebook.add(inspect, text="Inspector")
        notebook.add(editor, text="Edit item")
        notebook.add(creator, text="New content")
        notebook.add(generator, text="Variant generator")
        notebook.add(recipes, text="Multi-axis recipes")
        notebook.add(assets, text="Model preview")
        notebook.add(diagnostics, text="Diagnostics")
        notebook.add(relationships, text="References")
        notebook.add(recovery, text="History / recovery")
        self.notebook = notebook
        ttk.Label(inspect, text="Authored + inherited definition", style="Heading.TLabel").pack(anchor="w")
        self.info = self._text(inspect, wrap="none")
        ttk.Label(editor, text="Edit selected item • inherited values remain in the Inspector", style="Heading.TLabel").pack(anchor="w")
        edit_fields = ttk.Frame(editor)
        edit_fields.pack(fill="x")
        self._new_entry(edit_fields, "Display name (blank = inherit)", self.edit_name, 0)
        self._new_entry(edit_fields, "Material (blank = inherit)", self.edit_material, 1)
        self._new_entry(edit_fields, "Model (blank = inherit)", self.edit_model, 2)
        self._new_combo(edit_fields, "Abstract", self.edit_abstract, ["inherit", "true", "false"], 3, readonly=True)
        ttk.Button(editor, text="Update YAML from fields", command=self._fields_to_yaml).pack(anchor="w", pady=4)
        ttk.Label(editor, text="Advanced YAML for this item only. Existing file comments are retained where possible; review the full file diff.", wraplength=850).pack(anchor="w")
        self.edit_text = self._text(editor, wrap="none")
        self.edit_text.configure(height=10, state="normal")
        self.edit_text.bind("<<Modified>>", self._editor_changed)
        edit_actions = ttk.Frame(editor)
        edit_actions.pack(fill="x")
        ttk.Button(edit_actions, text="Preview YAML edits", command=self._preview_edit).pack(side="left")
        self.edit_apply = ttk.Button(edit_actions, text="Apply reviewed edit", command=self._apply_edit, state="disabled")
        self.edit_apply.pack(side="left", padx=8)
        self.edit_diff = self._text(editor, wrap="none")
        self.edit_diff.configure(height=8)
        ttk.Label(creator, text="Create a new item, furniture or vehicle configuration", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(creator, text="Link an existing model. Output is a new YAML file; existing authored configurations stay intact.", style="Sub.TLabel").pack(anchor="w", pady=(0, 10))
        new_fields = ttk.Frame(creator)
        new_fields.pack(fill="x")
        self.new_pack_box = self._new_combo(new_fields, "Pack namespace", self.new_namespace, [], 0)
        self._new_combo(new_fields, "Content type", self.new_kind, ["item", "furniture", "vehicle"], 1, readonly=True)
        self._new_entry(new_fields, "Item ID", self.new_name, 2)
        self._new_entry(new_fields, "Display name", self.new_label, 3)
        self._new_entry(new_fields, "Base material", self.new_material, 4)
        self.new_model_box = self._new_combo(new_fields, "Existing model", self.new_model, [], 5)
        self.new_namespace.trace_add("write", lambda *_: self._load_model_refs())
        form_actions = ttk.Frame(creator)
        form_actions.pack(fill="x", pady=(12, 5))
        ttk.Button(form_actions, text="Preview new configuration", style="Accent.TButton", command=self._preview_new).pack(side="left")
        self.new_apply_button = ttk.Button(form_actions, text="Create with backup", state="disabled", command=self._apply_new)
        self.new_apply_button.pack(side="left", padx=8)
        self.new_preview = self._text(creator, wrap="none")
        ttk.Label(generator, text="Inherited material family generator", style="Heading.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(generator, text="Select an item such as oak_table or white_wool_chair in the explorer.", style="Sub.TLabel").pack(anchor="w", pady=(0, 10))
        settings = ttk.Frame(generator)
        settings.pack(fill="x")
        self._combo(settings, "Family", self.family, ["wood", "wool"], 0)
        self._combo(settings, "Target", self.target, list(SUPPORTED_TARGETS), 1)
        self._combo(settings, "Model method", self.strategy, ["alias", "clone"], 2)
        ttk.Label(settings, text="Texture slot (blank = auto)").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(settings, textvariable=self.texture_slot).grid(row=3, column=1, sticky="ew", padx=8)
        settings.columnconfigure(1, weight=1)
        ttk.Label(generator, text="Choose materials (Ctrl/Shift for multi-select)", style="Sub.TLabel").pack(anchor="w", pady=(12, 4))
        palette_row = ttk.Frame(generator)
        palette_row.pack(fill="x")
        self.choices = tk.Listbox(palette_row, selectmode="extended", exportselection=False, height=5,
                                  bg="#1b2b39", fg="white", selectbackground="#237d97")
        self.choices.pack(side="left", fill="x", expand=True)
        buttons = ttk.Frame(palette_row)
        buttons.pack(side="left", padx=8)
        ttk.Button(buttons, text="All", command=lambda: self.choices.select_set(0, "end")).pack(fill="x", pady=2)
        ttk.Button(buttons, text="None", command=lambda: self.choices.selection_clear(0, "end")).pack(fill="x", pady=2)
        actions = ttk.Frame(generator)
        actions.pack(fill="x", pady=(12, 6))
        ttk.Button(actions, text="Preview changes", command=self._plan, style="Accent.TButton").pack(side="left")
        self.apply_button = ttk.Button(actions, text="Apply with backup", command=self._apply, state="disabled")
        self.apply_button.pack(side="left", padx=8)
        ttk.Checkbutton(actions, text="Show YAML / JSON diff", variable=self.show_diff, command=self._update_plan).pack(side="left", padx=8)
        ttk.Checkbutton(generator, text="Include matching animation, blockstate, display-part and vehicle chest items", variable=self.include_dependencies,
                        command=self._invalidate_plan).pack(anchor="w")
        self.plan_text = self._text(generator, wrap="none")
        ttk.Label(recipes, text="Explicit texture-axis recipes", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(recipes, text="Bind each model texture slot to a named axis. Include state items explicitly. Recipe metadata is stored with output ownership, outside plugin definitions.", wraplength=850).pack(anchor="w")
        recipe_actions = ttk.Frame(recipes)
        recipe_actions.pack(fill="x", pady=6)
        ttk.Button(recipe_actions, text="Load recipe / manifest", command=self._load_recipe_file).pack(side="left")
        ttk.Button(recipe_actions, text="Preview recipe", command=self._preview_recipe).pack(side="left", padx=6)
        self.recipe_apply = ttk.Button(recipe_actions, text="Apply reviewed recipe", command=self._apply_recipe, state="disabled")
        self.recipe_apply.pack(side="left")
        self.recipe_text = self._text(recipes, wrap="none")
        self.recipe_text.configure(state="normal", height=14)
        self.recipe_text.insert("1.0", "recipe_schema: 1\nid: material-color\nsource: voxel:oak_table\ntarget: mc-26.3\nstrategy: alias\naxes:\n  wood:\n    oak: minecraft:block/oak_planks\n    spruce: minecraft:block/spruce_planks\n  color:\n    white: minecraft:block/white_wool\n    red: minecraft:block/red_wool\ntexture_slots:\n  wood: wood\n  cloth: color\nitems:\n  voxel:oak_table: '{wood}_{color}_table'\n")
        self.recipe_text.edit_modified(False)
        self.recipe_text.bind("<<Modified>>", self._recipe_changed)
        self.recipe_diff = self._text(recipes, wrap="none")
        self.recipe_diff.configure(height=12)
        ttk.Label(assets, text="Model inspector", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        self.preview = ModelPreview(assets)
        self.preview.pack(fill="x")
        self.model_info = self._text(assets, wrap="none")
        ttk.Label(diagnostics, text="Workspace diagnostics", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(diagnostics, text="Local lint is structural only. Optional Java validation runs against a temporary snapshot of saved files (not unsaved editor changes).", style="Sub.TLabel", wraplength=900).pack(anchor="w", pady=(0, 6))
        ttk.Button(diagnostics, text="Run local checks", command=self._diagnose).pack(anchor="w", pady=(0, 10))
        java_settings = ttk.Frame(diagnostics)
        java_settings.pack(fill="x")
        ttk.Label(java_settings, text="Java classpath file").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(java_settings, textvariable=self.java_classpath).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(java_settings, text="Browse…", command=self._choose_java_classpath).grid(row=0, column=2)
        ttk.Label(java_settings, text="Render allocations (optional)").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(java_settings, textvariable=self.java_allocations).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(java_settings, text="Browse…", command=self._choose_java_allocations).grid(row=1, column=2, padx=2)
        ttk.Button(java_settings, text="Clear", command=lambda: self.java_allocations.set("")).grid(row=1, column=3, padx=2)
        java_settings.columnconfigure(1, weight=1)
        ttk.Button(diagnostics, text="Validate saved content with VoxelCore Java", command=self._validate_java).pack(anchor="w", pady=(8, 6))
        self.diagnostics_text = self._text(diagnostics)
        ttk.Label(relationships, text="Known incoming and outgoing dependencies", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(relationships, text="Unknown plugin fields, glyphs and external vanilla assets are not fully indexed. Unused candidates are not safe-delete advice.", wraplength=800).pack(anchor="w")
        self.references_text = self._text(relationships, wrap="none")
        ttk.Label(recovery, text="Review a snapshot before restoring or reapplying it", style="Heading.TLabel").pack(anchor="w")
        self.history = ttk.Treeview(recovery, columns=("state", "pack"), show="tree headings", height=7)
        self.history.heading("#0", text="Snapshot")
        self.history.heading("state", text="State")
        self.history.heading("pack", text="Pack")
        self.history.pack(fill="x", pady=8)
        self.history.bind("<<TreeviewSelect>>", self._show_snapshot)
        history_actions = ttk.Frame(recovery)
        history_actions.pack(fill="x")
        for label, action in (("Undo", "undo"), ("Redo", "redo"), ("Recover interrupted operation", "recover")):
            ttk.Button(history_actions, text=label, command=lambda a=action: self._restore_snapshot(a)).pack(side="left", padx=4)
        self.history_text = self._text(recovery, wrap="none")
        self.snapshots = {}
        footer = ttk.Frame(self, padding=10)
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status, style="Sub.TLabel").pack(side="left")
        ttk.Label(footer, text="LOCAL • OFFLINE • NO SERVER RELOAD", style="Sub.TLabel").pack(side="right")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=120)
        self.progress.pack(side="left", padx=8)
        self._load_palette()
        self.after(80, self._poll_work)
        self.protocol("WM_DELETE_WINDOW", self._close)
        for variable in (self.edit_name, self.edit_material, self.edit_model, self.edit_abstract):
            variable.trace_add("write", self._form_changed)
        for variable in (self.strategy, self.texture_slot):
            variable.trace_add("write", lambda *_: self._invalidate_plan())
        self.choices.bind("<<ListboxSelect>>", lambda _: self._invalidate_plan())
        for variable in (self.new_namespace, self.new_name, self.new_label, self.new_kind, self.new_material, self.new_model):
            variable.trace_add("write", lambda *_: self._invalidate_new())

    def _recipe_changed(self, _=None):
        if self.recipe_text.edit_modified():
            self.recipe_plan = None
            self.recipe_apply.configure(state="disabled")
            self.recipe_text.edit_modified(False)

    def _load_recipe_file(self):
        if self._busy:
            return
        path = filedialog.askopenfilename(filetypes=[("Recipe or manifest", "*.yml *.yaml *.json")])
        if not path:
            return
        try:
            from .core import _read_yaml
            data = _read_yaml(Path(path))
            self.recipe_text.delete("1.0", "end")
            self.recipe_text.insert("1.0", yaml.safe_dump(data.get("recipe", data), sort_keys=False))
        except (ContentError, OSError, ValueError) as exc:
            messagebox.showerror("Cannot load recipe", str(exc))

    def _preview_recipe(self):
        if self._busy or not self.workspace:
            return
        text = self.recipe_text.get("1.0", "end-1c")
        workspace = self.workspace
        self.recipe_plan = None
        self.recipe_apply.configure(state="disabled")
        def work():
            if len(text.encode("utf-8")) > 3 * 1024 * 1024:
                raise ContentError("Recipe exceeds 3 MiB")
            return plan_recipe(workspace, yaml.load(text, Loader=UniqueSafeLoader))
        def planned(plan):
            if text != self.recipe_text.get("1.0", "end-1c") or workspace is not self.workspace:
                return
            from difflib import unified_diff
            diffs = []
            for output in plan.changed:
                old = output.path.read_text(encoding="utf-8").splitlines(keepends=True) if output.path.exists() else []
                new = output.payload.decode("utf-8").splitlines(keepends=True)
                diffs.append("".join(unified_diff(old, new, fromfile="before/"+output.path.name, tofile="after/"+output.path.name)))
            self._put(self.recipe_diff, plan.summary() + "\n\n" + "\n".join(diffs))
            self.recipe_plan = plan
            self.recipe_apply.configure(state="normal" if plan.changed else "disabled")
            self.status.set("Recipe diff ready for review.")
        self._run_work("Planning material combinations…", work, planned)

    def _apply_recipe(self):
        if self._busy or not self.recipe_plan:
            return
        if not messagebox.askyesno("Apply recipe?", f"Write {len(self.recipe_plan.changed)} reviewed files with a rollback snapshot?"):
            return
        plan = self.recipe_plan
        self._run_work("Applying recipe…", lambda: apply_plan(plan), lambda _: self._refresh())

    def _form_changed(self, *_):
        if not self._loading_editor and self.editor_id:
            self._fields_pending = True
            self.edit_dirty = True
            self.edit_plan = None
            self.edit_apply.configure(state="disabled")

    def _close(self):
        if self._busy:
            messagebox.showinfo("Operation in progress", "Wait for the current operation to finish before closing.")
            return
        if self.edit_dirty and not messagebox.askyesno("Discard unsaved edit?", "Close without saving the current item edit?"):
            return
        self.destroy()

    def _editor_changed(self, _=None):
        if self.edit_text.edit_modified():
            if not self._loading_editor:
                self.edit_dirty = True
                self.edit_plan = None
                self.edit_apply.configure(state="disabled")
            self.edit_text.edit_modified(False)

    def _set_editor(self, text):
        self._loading_editor = True
        self.edit_text.delete("1.0", "end")
        self.edit_text.insert("1.0", text)
        self.edit_text.edit_modified(False)
        self._loading_editor = False

    def _load_editor(self, ident):
        self.editor_id = ident if ident in self.workspace.items else None
        self.edit_dirty = False
        self.edit_plan = None
        self.edit_apply.configure(state="disabled")
        definition = self.workspace.items[ident].definition if self.editor_id else {}
        self._set_editor(yaml.safe_dump(definition, sort_keys=False, allow_unicode=True))
        self._loading_editor = True
        self.edit_name.set(definition.get("display_name", ""))
        self.edit_material.set(definition.get("material", ""))
        self.edit_model.set(definition.get("render", {}).get("model", ""))
        self.edit_abstract.set(str(definition["abstract"]).lower() if "abstract" in definition else "inherit")
        self._loading_editor = False
        self._fields_pending = False
        self._put(self.edit_diff, "Preview YAML edits to review the complete file diff.")

    def _fields_to_yaml(self):
        if self._busy or not self.editor_id:
            return
        try:
            definition = parse_item_text(self.edit_text.get("1.0", "end-1c"))
            for key, value in (("display_name", self.edit_name.get()), ("material", self.edit_material.get())):
                if value:
                    definition[key] = value
                else:
                    definition.pop(key, None)
            render = definition.setdefault("render", {})
            if self.edit_model.get():
                render["model"] = self.edit_model.get()
            else:
                render.pop("model", None)
            if not render:
                definition.pop("render", None)
            if self.edit_abstract.get() == "inherit":
                definition.pop("abstract", None)
            else:
                definition["abstract"] = self.edit_abstract.get() == "true"
            self._set_editor(yaml.safe_dump(definition, sort_keys=False, allow_unicode=True))
            self.edit_dirty = True
            self._fields_pending = False
            self.edit_plan = None
            self.edit_apply.configure(state="disabled")
        except (ContentError, ValueError) as exc:
            messagebox.showerror("Invalid YAML", str(exc))

    def _preview_edit(self):
        if self._busy or not self.editor_id:
            return
        if self._fields_pending:
            messagebox.showinfo("Update YAML first", "Use Update YAML from fields before previewing your visual field changes.")
            return
        workspace, ident = self.workspace, self.editor_id
        text = self.edit_text.get("1.0", "end-1c")
        self.edit_plan = None
        self.edit_apply.configure(state="disabled")
        def planned(plan):
            if ident != self.editor_id or text != self.edit_text.get("1.0", "end-1c"):
                self.status.set("Edit changed during preview; preview again.")
                return
            from difflib import unified_diff
            output = plan.outputs[0]
            before = output.path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
            after = output.payload.decode("utf-8-sig").splitlines(keepends=True)
            self._put(self.edit_diff, plan.summary() + "\n" + "".join(unified_diff(before, after, fromfile="before/"+output.path.name, tofile="after/"+output.path.name)))
            self.edit_plan = plan
            self.edit_apply.configure(state="normal" if plan.changed else "disabled")
            self.status.set("Edit preview ready; review the full file diff.")
        self._run_work("Checking item edit…", lambda: plan_edit_item(workspace, ident, parse_item_text(text)), planned)

    def _apply_edit(self):
        if self._busy or not self.edit_plan:
            return
        if not messagebox.askyesno("Apply item edit?", "Apply the reviewed file diff with a rollback snapshot?"):
            return
        plan = self.edit_plan
        def applied(snapshot):
            self.edit_dirty = False
            self.edit_plan = None
            messagebox.showinfo("Saved", f"Item saved. Snapshot: {snapshot}")
            self._refresh()
        self._run_work("Saving reviewed item…", lambda: apply_plan(plan), applied)

    def _invalidate_plan(self):
        self.current_plan = None
        self.apply_button.configure(state="disabled")

    def _invalidate_new(self):
        self.new_plan = None
        self.new_apply_button.configure(state="disabled")

    def _run_work(self, label, work, success):
        if self._busy:
            return
        self._busy = True
        self.status.set(label)
        self.progress.start(12)
        def run():
            try:
                self._results.put((success, work(), None))
            except Exception as exc:
                self._results.put((success, None, exc))
        # Non-daemon: closing a window cannot abruptly kill an active disk write.
        threading.Thread(target=run, name="content-manager-worker").start()

    def _poll_work(self):
        try:
            callback, result, error = self._results.get_nowait()
        except queue.Empty:
            pass
        else:
            self._busy = False
            self.progress.stop()
            if error is not None:
                self.status.set(str(error))
                messagebox.showerror("Operation failed", str(error))
            else:
                try:
                    callback(result)
                except (ContentError, OSError, ValueError, KeyError) as exc:
                    self.status.set(str(exc))
                    messagebox.showerror("Workspace error", str(exc))
        self.after(80, self._poll_work)

    def _load_history(self):
        self.history.delete(*self.history.get_children())
        self.snapshots.clear()
        for pack in self.workspace.packs.values():
            pending_snapshots(pack.root)  # validate metadata paths before listing
            for path in sorted((pack.root / ".contentmanager/backups").glob("*/snapshot.json"), reverse=True):
                data = json.loads(path.read_text(encoding="utf-8"))
                node = self.history.insert("", "end", text=path.parent.name, values=(data.get("state", "committed (legacy)"), pack.namespace))
                self.snapshots[node] = (pack.root, path.parent, data)

    def _show_snapshot(self, _=None):
        selected = self.history.selection()
        if selected and selected[0] in self.snapshots:
            _, path, data = self.snapshots[selected[0]]
            self._put(self.history_text, str(path) + "\n\n" + json.dumps(data, indent=2))

    def _restore_snapshot(self, action):
        if self._busy:
            return
        selected = self.history.selection()
        if not selected or selected[0] not in self.snapshots:
            return
        pack, path, data = self.snapshots[selected[0]]
        if not messagebox.askyesno("Confirm " + action, f"{action.title()} {len(data['changes'])} recorded files?\n{path}\n\nExternal edits will cause a conflict."):
            return
        self._run_work(action.title() + " snapshot…", lambda: restore(pack, path, redo=action == "redo", recover=action == "recover"), lambda _: self._refresh())

    def _new_entry(self, parent, name, variable, row):
        ttk.Label(parent, text=name).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        parent.columnconfigure(1, weight=1)

    def _new_combo(self, parent, name, variable, choices, row, readonly=False):
        ttk.Label(parent, text=name).grid(row=row, column=0, sticky="w", pady=5)
        widget = ttk.Combobox(parent, textvariable=variable, values=choices, state="readonly" if readonly else "normal")
        widget.grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        parent.columnconfigure(1, weight=1)
        return widget

    def _load_model_refs(self):
        if not self.workspace:
            return
        namespace = self.new_namespace.get()
        if namespace not in self.workspace.packs:
            self.new_model_box.configure(values=[])
            return
        pack = self.workspace.packs[namespace]
        model_root = pack.root / "assets" / namespace / "models"
        refs = []
        if model_root.is_dir():
            for file in model_root.rglob("*.json"):
                if file.is_symlink():
                    continue
                try:
                    refs.append(f"{namespace}:{file.relative_to(model_root).with_suffix('').as_posix()}")
                except ValueError:
                    pass
        self.new_model_box.configure(values=sorted(refs))
        if refs and not self.new_model.get():
            self.new_model.set(sorted(refs)[0])

    def _preview_new(self):
        if self._busy:
            return
        if not self.workspace:
            messagebox.showinfo("Open workspace", "Open a VoxelCore pack first.")
            return
        try:
            self.new_plan = plan_new_item(self.workspace, self.new_namespace.get(), self.new_name.get(),
                                          self.new_label.get(), self.new_model.get(), self.new_kind.get(),
                                          self.new_material.get())
            f = self.new_plan.outputs[0]
            self._put(self.new_preview, self.new_plan.summary() + "\n\n--- Generated YAML ---\n" + f.payload.decode("utf-8"))
            self.new_apply_button.configure(state="normal")
        except (ContentError, OSError, ValueError) as ex:
            self.new_plan = None
            self.new_apply_button.configure(state="disabled")
            self._put(self.new_preview, str(ex))

    def _apply_new(self):
        if self._busy:
            return
        if not self.new_plan:
            return
        if not messagebox.askyesno("Create definition", "Write this configuration file to the workspace?\nA rollback snapshot will be created."):
            return
        plan = self.new_plan
        def created(backup):
            messagebox.showinfo("Created", f"Definition created.\nBackup: {backup}\n\nRun VoxelCore validation before publishing.")
            self._refresh()
        self._run_work("Creating approved definition…", lambda: apply_plan(plan), created)

    def _combo(self, parent, name, var, choices, row):
        ttk.Label(parent, text=name).grid(row=row, column=0, sticky="w", pady=4)
        box = ttk.Combobox(parent, textvariable=var, values=choices, state="readonly")
        box.grid(row=row, column=1, sticky="ew", padx=8, pady=4)

    def _text(self, parent, wrap="word"):
        t = scrolledtext.ScrolledText(parent, font=("Consolas", 10), wrap=wrap, bg="#14222f",
                                      fg="#e5edf5", insertbackground="white", relief="flat", padx=10, pady=10)
        t.pack(fill="both", expand=True, pady=8)
        t.configure(state="disabled")
        return t

    def _put(self, widget, message):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", message)
        widget.configure(state="disabled")

    def _choose_workspace(self):
        directory = filedialog.askdirectory(title="Select plugins/VoxelCore/content or a pack")
        if directory:
            self._open(directory)

    def _open(self, path):
        if self._busy:
            return
        if self.edit_dirty and not messagebox.askyesno("Discard unsaved edit?", "Open/refresh the workspace and discard the current item edit?"):
            return
        def load():
            workspace = Workspace(path)
            return workspace, ReferenceGraph(workspace)
        def loaded(result):
            self.workspace, self.graph = result
            self.path.set(str(self.workspace.root))
            self._invalidate_plan()
            self._invalidate_new()
            self.recipe_plan = None
            self.recipe_apply.configure(state="disabled")
            self.new_pack_box.configure(values=sorted(self.workspace.packs))
            if self.new_namespace.get() not in self.workspace.packs:
                self.new_namespace.set(next(iter(sorted(self.workspace.packs))))
            self._load_model_refs()
            self.current_id = None
            self._load_editor(None)
            self._put(self.info, "Select an item in the Content explorer.")
            self._build_tree()
            self._diagnose()
            self._load_history()
            self.status.set(f"Loaded {len(self.workspace.packs)} pack(s), {len(self.workspace.items)} items")
        self._run_work("Reading content and model dependencies…", load, loaded)

    def _refresh(self):
        if self.workspace:
            self._open(self.workspace._pack_dirs[0] if len(self.workspace._pack_dirs) == 1 else self.workspace.root)

    def _build_tree(self):
        if self._busy:
            return
        self.tree.delete(*self.tree.get_children())
        self.tree_items.clear()
        if not self.workspace:
            return
        query = self.search.get().lower().strip()
        for category in ("Furniture", "Vehicle", "Item", "Block", "UI glyph"):
            group = self.tree.insert("", "end", text=category, open=True)
            if category in ("Furniture", "Vehicle", "Item"):
                ids = []
                for key in self.workspace.items:
                    try:
                        kind = self.workspace.kind(key)
                    except (ContentError, ValueError, TypeError):
                        kind = "Item"
                    if kind == category:
                        ids.append(key)
            else:
                ids = list(self.workspace.blocks if category == "Block" else self.workspace.glyphs)
            for ident in sorted(ids):
                if query in ident.lower():
                    node = self.tree.insert(group, "end", text=ident)
                    self.tree_items[node] = ident
            if not self.tree.get_children(group):
                self.tree.delete(group)

    def _on_tree_select(self, _=None):
        if self._busy:
            return
        selected = self.tree.selection()
        if not selected or selected[0] not in self.tree_items or not self.workspace:
            return
        ident = self.tree_items[selected[0]]
        if ident == self.current_id:
            return
        if self.edit_dirty and not messagebox.askyesno("Discard unsaved edit?", "Select another item and discard the current edit?"):
            for node, key in self.tree_items.items():
                if key == self.current_id:
                    self.tree.selection_set(node)
                    break
            return
        self._load_editor(ident)
        self.current_id = ident
        self.current_plan = None
        self.apply_button.configure(state="disabled")
        if ident in self.workspace.items:
            try:
                self._put(self.info, self.workspace.describe(ident))
                path = self.workspace.model_file(ident)
                resolved_model = ModelResolver(self.workspace).resolve(self.workspace.resolve_item(ident)["render"]["model"])
                self.preview.load_resolved(resolved_model.effective)
                self._put(self.model_info, f"Model file: {path}\n\n" + (path.read_text(encoding="utf-8") if path.is_file() else "Missing model file"))
            except (ContentError, OSError, ValueError) as ex:
                self._put(self.info, f"{ident}\n{ex}")
                self.preview.load(None)
        else:
            collection = self.workspace.blocks if ident in self.workspace.blocks else self.workspace.glyphs
            _, file, definition = collection[ident]
            self._put(self.info, f"{ident}\nFile: {file}\n\n" + json.dumps(definition, indent=2))
            self.preview.load(None)
        self._put(self.plan_text, "Select material family and click Preview changes.")
        if self.graph:
            node = "item:" + ident
            edges = self.graph.incoming(node) + self.graph.outgoing(node)
            self._put(self.references_text, "\n".join(f"{e.source} --{e.relation}--> {e.target}" for e in edges) or "No known references")
        self.status.set(f"Selected {ident}")

    def _load_palette(self):
        if not hasattr(self, "choices"):
            return
        self.choices.delete(0, "end")
        try:
            palette = _palette(self.family.get(), self.target.get())
        except ContentError:
            palette = ()
        for value in palette:
            self.choices.insert("end", value)
        self.choices.select_set(0, "end")
        self.current_plan = None
        self.apply_button.configure(state="disabled")

    def _plan(self):
        if self._busy:
            return
        if not self.workspace or self.current_id not in self.workspace.items:
            messagebox.showinfo("Select an item", "Select an item, furniture or vehicle definition first.")
            return
        workspace, ident = self.workspace, self.current_id
        values = tuple(self.choices.get(i) for i in self.choices.curselection())
        args = (workspace, ident, self.family.get(), self.target.get(), self.strategy.get(),
                self.texture_slot.get().strip(), values, self.include_dependencies.get())
        self._invalidate_plan()
        def planned(plan):
            # Changing selection/settings while a worker runs invalidates its result.
            now = (self.workspace, self.current_id, self.family.get(), self.target.get(), self.strategy.get(),
                   self.texture_slot.get().strip(), tuple(self.choices.get(i) for i in self.choices.curselection()), self.include_dependencies.get())
            if now != args:
                self.status.set("Settings changed during preview; preview again.")
                return
            self.current_plan = plan
            self._update_plan()
            self.apply_button.configure(state="normal" if plan.changed else "disabled")
            self.status.set(f"Preview: {len(plan.changed)} proposed file changes. Nothing written.")
        self._run_work("Resolving models and planning variants…", lambda: plan_family(*args), planned)

    def _update_plan(self):
        if not self.current_plan:
            return
        msg = self.current_plan.summary()
        if self.show_diff.get():
            from difflib import unified_diff
            blocks = []
            for f in self.current_plan.changed:
                old = f.path.read_text(encoding="utf-8").splitlines(keepends=True) if f.path.is_file() else []
                new = f.payload.decode("utf-8").splitlines(keepends=True)
                blocks.append("".join(unified_diff(old, new, fromfile="before/" + f.path.name,
                                                   tofile="after/" + f.path.name)))
            msg += "\n\n--- YAML / JSON diff ---\n" + "\n".join(blocks)
        self._put(self.plan_text, msg)

    def _apply(self):
        if self._busy:
            return
        if not self.current_plan or not self.current_plan.changed:
            return
        if not messagebox.askyesno("Apply generated files?", f"Write {len(self.current_plan.changed)} files?\n"
                                    "A backup snapshot will be created.\n"
                                    "No running server will be reloaded.\n\n"
                                    "Check the diff and validate in VoxelCore before deployment."):
            return
        plan = self.current_plan
        def applied(snapshot):
            messagebox.showinfo("Generated", f"Applied output.\nSnapshot: {snapshot}\n\nRun VoxelCore validation before publishing.")
            self._refresh()
        self._run_work("Applying approved files…", lambda: apply_plan(plan), applied)

    def _choose_java_classpath(self):
        if self._busy:
            return
        path = filedialog.askopenfilename(
            title="Select VoxelCore Java runtime classpath text file",
            filetypes=[("Classpath text", "*.txt"), ("All files", "*.*")]
        )
        if path:
            self.java_classpath.set(path)

    def _choose_java_allocations(self):
        if self._busy:
            return
        path = filedialog.askopenfilename(
            title="Select an existing render-allocation manifest (copied, never edited)",
            filetypes=[("YAML files", "*.yml *.yaml"), ("All files", "*.*")]
        )
        if path:
            self.java_allocations.set(path)

    def _validate_java(self):
        if self._busy:
            return
        if not self.workspace:
            messagebox.showinfo("Open workspace", "Open a VoxelCore content pack before validation.")
            return
        classpath = self.java_classpath.get().strip()
        if not classpath:
            messagebox.showinfo(
                "Java classpath required",
                "Build VoxelCore with Maven and select its Java dependency classpath file.\n"
                "See docs/JAVA-VALIDATION.md for setup instructions."
            )
            return
        if self.edit_dirty and not messagebox.askyesno(
                "Unsaved edits excluded",
                "Java validation reads the saved workspace from disk. Your unsaved item editor "
                "changes are NOT included. Continue?"):
            return
        workspace = self.workspace
        target = self.target.get()
        allocations = self.java_allocations.get().strip() or None
        from .validation import validate_java
        self._put(self.diagnostics_text,
                  f"Validating saved {target} content using a staged copy…\n"
                  "The original pack and allocation files are never passed to the Java compiler.")
        def completed(result):
            lines = [
                f"VoxelCore Java validation: {'PASSED' if result.success else 'FAILED'}",
                f"Target: {result.target}",
                f"Snapshot files: {result.input_files}",
                f"Input SHA256: {result.input_sha256}",
                "Compiler classpath provenance: not automatically attested",
                "Paper and addon runtime compatibility: NOT tested",
                ""
            ]
            if result.success:
                lines.extend([
                    f"Rendered items: {result.rendered_items}",
                    f"Rendered blocks: {result.rendered_blocks}",
                    f"Copied assets: {result.copied_assets}", ""
                ])
            if result.stdout.strip():
                lines.extend(["Java output:", result.stdout.strip(), ""])
            if result.stderr.strip():
                lines.extend(["Java diagnostics:", result.stderr.strip()])
            self._put(self.diagnostics_text, "\n".join(lines))
            self.status.set("Java validation passed on a staged snapshot" if result.success else
                            "Java validation failed; review the Diagnostics tab")
        self._run_work("Running staged VoxelCore Java validation…",
                       lambda: validate_java(workspace, classpath, target, allocations),
                       completed)

    def _diagnose(self):
        if not self.workspace:
            return
        from .lint import lint_workspace
        report = lint_workspace(self.workspace)
        self._put(self.diagnostics_text, report.format_text())


def launch(root_path: str | None = None):
    app = ContentManagerApp(root_path)
    app.mainloop()
