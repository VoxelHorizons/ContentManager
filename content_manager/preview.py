"""Dependency-free Tk canvas geometry approximation for authored block/item models.

Does not emulate game lighting, shaders, full parent chains or vanilla model
transforms. Those are deliberately labeled as unverified in the application.
"""
from __future__ import annotations
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk


class ModelPreview(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, height=285, background="#172330", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.message = ttk.Label(self, text="Approximate cuboid preview (not Minecraft validation)")
        self.message.pack(anchor="w")
        self.model: dict = {}
        self.canvas.bind("<Configure>", lambda _: self.draw())

    def load(self, path: Path | None):
        self.model = {}
        if path and path.is_file():
            try:
                self.model = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        self.draw()

    def draw(self):
        c = self.canvas
        c.delete("all")
        width, height = max(c.winfo_width(), 360), max(c.winfo_height(), 270)
        scale = min(width / 48, height / 44)
        def project(p):
            x, y, z = p
            return (width/2 + (x-z)*0.72*scale, height*0.73 - (x+z)*0.34*scale - y*0.9*scale)
        def face(points, color):
            flat = [n for p in points for n in project(p)]
            c.create_polygon(flat, fill=color, outline="#8995a6", width=1)
        elements = self.model.get("elements", []) if isinstance(self.model, dict) else []
        if not isinstance(elements, list) or not elements:
            c.create_text(width/2, height/2, text="No inline cuboid elements\n(parent geometry / custom transforms not resolved)",
                          fill="#d0d9e3", justify="center")
            return
        # Sort far-to-near; represent visible top, front and side surfaces.
        for e in sorted(elements, key=lambda v: sum(v.get("from", [0, 0, 0])) if isinstance(v, dict) else 0):
            try:
                x0,y0,z0 = [float(n) for n in e["from"]]
                x1,y1,z1 = [float(n) for n in e["to"]]
                if not all(-64 <= v <= 64 for v in (x0,y0,z0,x1,y1,z1)):
                    continue
                face([(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)], "#577b9e")
                face([(x1,y0,z0),(x1,y0,z1),(x1,y1,z1),(x1,y1,z0)], "#416382")
                face([(x0,y1,z0),(x1,y1,z0),(x1,y1,z1),(x0,y1,z1)], "#80a5c3")
            except (KeyError, TypeError, ValueError, IndexError):
                continue
