"""Cliente mínimo de Webpay Plus (API REST de Transbank), sin SDK.

Por defecto usa el ambiente de INTEGRACIÓN con las credenciales públicas de Transbank:
no se cobra nada real. Para producción define estas variables de entorno:

    WEBPAY_AMBIENTE=produccion
    WEBPAY_CODIGO_COMERCIO=<código de comercio entregado por Transbank>
    WEBPAY_API_KEY=<llave secreta entregada por Transbank>

Tarjeta de prueba (integración): VISA 4051 8856 0044 6623, CVV 123, cualquier fecha futura.
En el formulario del banco: RUT 11.111.111-1 y clave 123.
"""
import os

import requests

VERSION = "v1.2"
HOSTS = {
    "integracion": "https://webpay3gint.transbank.cl",
    "produccion": "https://webpay3g.transbank.cl",
}
# Credenciales públicas de integración (publicadas por Transbank; no son secretas)
COMERCIO_INTEGRACION = "597055555532"
LLAVE_INTEGRACION = "579B532A7440BB0C9079DED94D31EA1615BACEB56610332264630D42D0A36B1C"


class ErrorWebpay(Exception):
    """Transbank no respondió o rechazó la solicitud."""


class ClienteWebpay:
    def __init__(self, ambiente=None, comercio=None, llave=None, sesion=None):
        self.ambiente = (ambiente or os.environ.get("WEBPAY_AMBIENTE") or "integracion").lower()
        if self.ambiente not in HOSTS:
            raise ValueError("WEBPAY_AMBIENTE debe ser 'integracion' o 'produccion'")
        self.comercio = comercio or os.environ.get("WEBPAY_CODIGO_COMERCIO")
        self.llave = llave or os.environ.get("WEBPAY_API_KEY")
        if self.ambiente == "integracion":
            self.comercio = self.comercio or COMERCIO_INTEGRACION
            self.llave = self.llave or LLAVE_INTEGRACION
        elif not (self.comercio and self.llave):
            raise ValueError("En producción define WEBPAY_CODIGO_COMERCIO y WEBPAY_API_KEY")
        self.sesion = sesion or requests

    @property
    def es_prueba(self) -> bool:
        return self.ambiente != "produccion"

    def _url(self, token=None) -> str:
        base = f"{HOSTS[self.ambiente]}/rswebpaytransaction/api/webpay/{VERSION}/transactions"
        return f"{base}/{token}" if token else base

    def _cabeceras(self) -> dict:
        return {"Tbk-Api-Key-Id": self.comercio, "Tbk-Api-Key-Secret": self.llave,
                "Content-Type": "application/json"}

    def _llamar(self, metodo, url, **kwargs):
        try:
            r = self.sesion.request(metodo, url, headers=self._cabeceras(), timeout=20, **kwargs)
        except requests.RequestException as e:
            raise ErrorWebpay(f"No se pudo contactar a Transbank: {e}") from e
        if r.status_code != 200:
            raise ErrorWebpay(f"Transbank respondió {r.status_code}: {r.text[:200]}")
        return r.json()

    def crear(self, buy_order: str, session_id: str, monto: int, url_retorno: str) -> dict:
        """Abre la transacción. Devuelve {'token': ..., 'url': ...}: el navegador debe enviar token_ws a esa URL."""
        return self._llamar("POST", self._url(), json={
            "buy_order": buy_order, "session_id": session_id, "amount": int(monto), "return_url": url_retorno})

    def confirmar(self, token: str) -> dict:
        """Confirma (commit) la transacción: hay que hacerlo siempre al volver del banco."""
        return self._llamar("PUT", self._url(token))
