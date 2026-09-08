import sys
from pathlib import Path

# Permite importar web/app.py sin instalar el proyecto como paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
