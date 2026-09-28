# -*- coding: utf-8 -*-
"""
Lector de fuentes primarias — VERSIÓN NUBE, UN SOLO ARCHIVO.

Pensado para correr en GitHub Actions, sin tu computadora encendida.
No necesita config.py: la clave de FRED se lee de una variable de entorno.

Escribe macro.json en la raíz del repo. El workflow lo commitea solo.

Dependencia única: requests
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone

BOLIVIA = timezone(timedelta(hours=-4))
UA = {"User-Agent": "feed-andres/1.0 (uso personal)"}
SALIDA = "macro.json"
RAW_CHARS = 6000

FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()

FRED_SERIES = {
    "us10y": "DGS10",
    "us2y": "DGS2",
    "us30y": "DGS30",
    "vix": "VIXCLS",
    "dxy": "DTWEXBGS",
    "wti": "DCOILWTICO",
}

RELEASES = [
    {"id": "cpi", "nombre": "IPC (CPI)", "hora_et": "08:30", "fuente": "BLS",
     "url": "https://www.bls.gov/news.release/cpi.nr0.htm"},
    {"id": "empsit", "nombre": "Situación del empleo (nóminas)", "hora_et": "08:30",
     "fuente": "BLS", "url": "https://www.bls.gov/news.release/empsit.nr0.htm"},
    {"id": "ppi", "nombre": "IPP (PPI)", "hora_et": "08:30", "fuente": "BLS",
     "url": "https://www.bls.gov/news.release/ppi.nr0.htm"},
    {"id": "jolts", "nombre": "JOLTS — vacantes", "hora_et": "10:00", "fuente": "BLS",
     "url": "https://www.bls.gov/news.release/jolts.nr0.htm"},
    {"id": "claims", "nombre": "Peticiones semanales de desempleo", "hora_et": "08:30",
     "fuente": "DOL", "days": [3], "url": "https://www.dol.gov/ui/data.pdf"},
    {"id": "pce", "nombre": "Ingreso personal y PCE", "hora_et": "08:30", "fuente": "BEA",
     "url": "https://www.bea.gov/news/current-releases"},
    {"id": "retail", "nombre": "Ventas minoristas", "hora_et": "08:30", "fuente": "Census",
     "url": "https://www.census.gov/retail/marts/www/marts_current.pdf"},
    {"id": "durables", "nombre": "Bienes durables", "hora_et": "08:30", "fuente": "Census",
     "url": "https://www.census.gov/manufacturing/m3/adv/pdf/durgd.pdf"},
    {"id": "fomc", "nombre": "Comunicado del FOMC", "hora_et": "14:00", "fuente": "Fed",
     "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary.htm"},
]

PATRONES = {
    "cpi": [
        (r"increased\s+([\d.]+)\s*percent.{0,40}?(?:in|during)\s+\w+,?\s*"
         r"(?:seasonally adjusted|on a seasonally adjusted basis)", "ipc_mensual_pct"),
        (r"(?:rose|increased)\s+([\d.]+)\s*percent\s+(?:before seasonal adjustment\s+)?"
         r"over the last 12 months", "ipc_interanual_pct"),
    ],
    "empsit": [
        (r"[Nn]onfarm payroll employment (?:rose|increased|changed little|fell|declined)"
         r"[^.]{0,60}?by\s+([\d,]+),?000", "nominas_miles"),
        (r"unemployment rate\s+(?:was|remained|held|edged|changed little)[^.]{0,40}?"
         r"([\d.]+)\s*percent", "desempleo_pct"),
    ],
    "ppi": [(r"(?:rose|increased|advanced|fell|declined)\s+([\d.]+)\s*percent\s+in\s+\w+",
             "ipp_mensual_pct")],
    "claims": [(r"advance figure for seasonally adjusted initial claims[^\d]{0,80}?([\d,]+)",
                "peticiones_iniciales")],
    "jolts": [(r"job openings\s+(?:was|were|changed little at|edged \w+ to|decreased to|"
               r"increased to)[^\d]{0,40}?([\d.]+)\s*million", "vacantes_millones")],
}

import requests   # noqa: E402


def hora_et():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4)))


def sello():
    b = datetime.now(BOLIVIA)
    return {
        "bolivia": b.strftime("%Y-%m-%d %H:%M:%S"),
        "bolivia_hora": b.strftime("%H:%M"),
        "utc_iso": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dia_semana": ["lunes", "martes", "miércoles", "jueves", "viernes",
                       "sábado", "domingo"][b.weekday()],
    }


def limpiar(t):
    t = re.sub(r"<script.*?</script>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t).replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", t).strip()


def extraer(rid, texto):
    out = {}
    for patron, campo in PATRONES.get(rid, []):
        m = re.search(patron, texto, flags=re.I)
        if m:
            v = m.group(1).replace(",", "")
            try:
                out[campo] = float(v)
            except ValueError:
                out[campo] = v
    return out


def fred(sid):
    if not FRED_API_KEY:
        return {"error": "falta el secreto FRED_API_KEY en el repositorio"}
    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                         params={"series_id": sid, "api_key": FRED_API_KEY,
                                 "file_type": "json", "sort_order": "desc", "limit": 6},
                         headers=UA, timeout=20)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        obs = [o for o in r.json().get("observations", [])
               if o.get("value") not in (".", None, "")]
        if not obs:
            return {"error": "sin observaciones"}
        d = {"valor": float(obs[0]["value"]), "fecha": obs[0]["date"]}
        if len(obs) > 1:
            d["previo"] = float(obs[1]["value"])
            d["cambio"] = round(d["valor"] - d["previo"], 4)
        return d
    except Exception as e:
        return {"error": str(e)}


def toca(rel, ahora):
    """
    Ventana de captura amplia: GitHub Actions dispara con retraso variable,
    a veces 10 minutos o más. Por eso aceptamos desde el minuto programado
    hasta 45 minutos después, y la firma del texto evita duplicados.
    """
    hh, mm = rel["hora_et"].split(":")
    obj = ahora.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    delta = (ahora - obj).total_seconds()
    if not (0 <= delta <= 2700):
        return False
    if ahora.weekday() > 4:
        return False
    if rel.get("days") and ahora.weekday() not in rel["days"]:
        return False
    return True


def bajar(rel):
    try:
        r = requests.get(rel["url"], headers=UA, timeout=25)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        if rel["url"].lower().endswith(".pdf"):
            return {"pdf": True, "bytes": len(r.content),
                    "nota": "PDF disponible; abrir la URL para ver las cifras"}
        texto = limpiar(r.text)
        return {"texto_crudo": texto[:RAW_CHARS], "cifras": extraer(rel["id"], texto)}
    except Exception as e:
        return {"error": str(e)}


def main():
    ts = sello()
    ahora = hora_et()

    previo = {}
    if os.path.exists(SALIDA):
        try:
            with open(SALIDA, encoding="utf-8") as f:
                previo = json.load(f)
        except Exception:
            previo = {}

    pubs = previo.get("publicaciones", {})

    for rel in RELEASES:
        if not toca(rel, ahora):
            continue
        res = bajar(rel)
        if "error" in res:
            print(f"{rel['id']}: {res['error']}")
            continue
        firma = res.get("texto_crudo", "")[:400]
        if pubs.get(rel["id"], {}).get("_firma") == firma:
            continue
        pubs[rel["id"]] = {
            "nombre": rel["nombre"], "fuente": rel["fuente"], "url": rel["url"],
            "capturado": ts, "hora_et_programada": rel["hora_et"],
            "_firma": firma, **res,
        }
        print(f"CAPTURADO: {rel['nombre']}")

    salida = {
        "_que_es": ("Datos macro leídos de las fuentes primarias de EE.UU. — BLS, "
                    "BEA, Census, DOL y la Fed — más contexto de FRED. Corre en "
                    "GitHub Actions, sin la computadora de Andrés."),
        "_como_leerlo": ("'contexto' trae el último valor de cada serie. "
                         "'publicaciones' guarda cada comunicado capturado: "
                         "'cifras' es extracción automática y puede fallar, "
                         "'texto_crudo' es el texto real. Ante la duda, vale el "
                         "texto crudo."),
        "_aviso_latencia": ("GitHub Actions no dispara con precisión de minuto: "
                            "puede retrasarse. La captura está abierta 45 minutos "
                            "desde la hora programada."),
        "generado": ts,
        "contexto": {k: fred(v) for k, v in FRED_SERIES.items()},
        "publicaciones": pubs,
    }

    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(f"escrito {SALIDA} — {ts['bolivia']}")


if __name__ == "__main__":
    main()