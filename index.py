"""Ponto de entrada pra Vercel — o runtime Python da Vercel procura uma
variável `app` (WSGI) dentro de api/*.py. O app de verdade continua
inteiro em app.py, na raiz do projeto (mesmo arquivo usado pra rodar
local com `python app.py`); este arquivo só importa e reexpõe."""
from app import app  # noqa: F401
