"""Bloquer un numéro chez Meta (repris de meta.js et bloques.js d'Alix FSP, 14.11.2026) : plus aucun message de lui
n'arrive, et lui ne peut plus écrire au numéro de l'agence. Meta ne le permet que pour un numéro qui a écrit dans les
dernières 24 heures ; sinon la liste des numéros bloqués de l'agent (stockage.Bloques) suffit.

L'appel passe par l'expéditeur WhatsApp du client (noyau.whatsapp.Expediteur : son client HTTP, l'adresse de l'API Graph,
le numéro et le jeton), sans rien y changer ; un agent sans numéro WhatsApp ne bloque rien chez Meta.
"""

from __future__ import annotations

import httpx

from noyau.whatsapp import chiffres


async def bloquer_chez_meta(exp, numero: str, bloquer: bool = True) -> tuple[bool | None, str]:
    """Bloque (ou débloque) ce numéro chez Meta : (fait, raison si non) ; fait vaut None sans numéro WhatsApp. Jamais
    d'exception : la liste de l'agent suffit."""
    client, graph, ident, auth = (getattr(exp, a, None) for a in ("_client", "_graph", "_numero", "_auth"))
    if client is None or not graph or not ident or not auth:
        return None, "pas de numéro WhatsApp"
    n = chiffres(numero)
    if not n:
        return False, "numéro illisible"
    try:
        r = await client.request("POST" if bloquer else "DELETE", f"{graph}/{ident}/block_users", headers=auth,
                                 json={"messaging_product": "whatsapp", "block_users": [{"user": n}]})
    except httpx.HTTPError as e:
        return False, type(e).__name__
    if r.status_code >= 400:
        return False, f"Meta {r.status_code} {r.text[:160]}"
    try:
        echecs = ((r.json() or {}).get("block_users") or {}).get("failed_users") or []
    except ValueError:
        echecs = []
    return (False, "Meta refuse ce numéro") if echecs else (True, "")
