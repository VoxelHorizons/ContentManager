"""PyInstaller entry point: native application plus deterministic launch smoke."""
import sys

from content_manager.app import ContentManagerApp


def main():
    app = ContentManagerApp()
    if '--smoke-test' in sys.argv:
        app.withdraw()
        app.update_idletasks()
        app.update()
        app.destroy()
        return 0
    app.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
