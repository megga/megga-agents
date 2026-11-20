"""Les outils d'Alix pour l'agent vocal d'ElevenLabs (noyau/appels.py) : des webhooks vers /appels/outils/<nom>, tirés des
outils de l'agent, pour que l'agent vocal et l'écrit aient les mêmes (scripts/appels_outils.py les écrit)."""

from __future__ import annotations

from .appels import PARAMETRES

CLIENT = {"type": "object", "description": "le client : son nom (exigé pour une nouvelle recherche), son téléphone, son e-mail.",
          "properties": {k: {"type": "string", "description": d} for k, d in
                         (("nom", "son nom"), ("telephone", "son téléphone"), ("email", "son e-mail"))}}

# Ce que l'outil fait à la voix, quand ce n'est pas tout ce qu'il fait à l'écrit.
DESCRIPTIONS = {"fiche_pdf": "Compose la fiche PDF d'une annonce du site (son slug ou sa référence) et l'envoie dans la conversation WhatsApp."}


def definitions(outils: dict, base: str, secret_id: str, delai: int = 30) -> list[dict]:
    """Les outils d'ElevenLabs (webhooks vers /appels/outils/<nom>), tirés des outils de l'agent : leurs descriptions et leurs
    paramètres, plus l'appelant et la conversation, que remplit ElevenLabs, jamais le modèle."""
    from agno.tools.function import Function

    def propriete(nom: str, s: dict) -> dict:
        s = next((x for x in s.get("anyOf", []) if x.get("type") != "null"), s) | {"description": s.get("description", "")}
        if s.get("type") == "object":  # le seul objet d'un outil d'appel : le client d'une recherche
            return CLIENT
        if s.get("type") == "array":
            return {"type": "array", "description": s["description"] or nom,
                    "items": {"type": (s.get("items") or {}).get("type", "string"), "description": nom}}
        return {"type": s.get("type", "string"), "description": s["description"] or nom}

    sortie = []
    for nom, f in outils.items():
        d = Function.from_callable(f).to_dict()
        params = d["parameters"]["properties"]
        permis = PARAMETRES.get(nom)
        props = {k: propriete(k, v) for k, v in params.items() if permis is None or k in permis}
        props["appelant"] = {"type": "string", "dynamic_variable": "system__caller_id"}
        props["conversation"] = {"type": "string", "dynamic_variable": "system__conversation_id"}
        requis = [k for k in d["parameters"].get("required", []) if k in props]
        sortie.append({"type": "webhook", "name": nom, "description": DESCRIPTIONS.get(nom) or " ".join(d["description"].split())[:1000],
                       "response_timeout_secs": delai, "api_schema": {
                           "url": f"{base}/outils/{nom}", "method": "POST",
                           "request_headers": {"Authorization": {"secret_id": secret_id}},
                           "request_body_schema": {"type": "object", "properties": props, "required": [*requis, "appelant"]}}})
    return sortie
