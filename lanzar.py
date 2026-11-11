"""Arranca la aplicación. Lo usan iniciar.bat e iniciar.command."""
import subprocess
import sys
from pathlib import Path


def preparar_streamlit() -> None:
    """Evita que Streamlit pregunte tu email la primera vez."""
    cred = Path.home() / ".streamlit" / "credentials.toml"
    if not cred.exists():
        cred.parent.mkdir(exist_ok=True)
        cred.write_text('[general]\nemail = ""\n', encoding="utf-8")


def actualizar() -> None:
    """Busca una versión nueva antes de abrir (si hay un sitio de actualizaciones configurado)."""
    try:
        from radar import actualizador

        mensaje = actualizador.al_arrancar()
        if mensaje:
            print("  " + mensaje)
    except Exception:  # noqa: BLE001 - nunca debe impedir abrir el programa
        pass


if __name__ == "__main__":
    preparar_streamlit()
    if "--sin-actualizar" not in sys.argv:
        actualizar()
    raiz = Path(__file__).resolve().parent
    # El aspecto y los ajustes van aquí (y no solo en .streamlit/config.toml) para que funcionen aunque esa carpeta falte
    ajustes = ["--theme.base", "dark", "--theme.primaryColor", "#fab219", "--theme.backgroundColor", "#0d0d0d",
               "--theme.secondaryBackgroundColor", "#1a1a19", "--theme.textColor", "#f0efec",
               "--browser.gatherUsageStats", "false", "--server.fileWatcherType", "none"]
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(raiz / "app.py"), *ajustes], cwd=raiz)
