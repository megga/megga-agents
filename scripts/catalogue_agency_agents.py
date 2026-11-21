"""Le catalogue des modèles prêts à l'emploi, tiré des 283 agents d'agency-agents (lot 11).

  python scripts/catalogue_agency_agents.py <clone d'agency-agents>             écrit le catalogue
  python scripts/catalogue_agency_agents.py <clone d'agency-agents> --verifier  compare sans écrire (code 1 si écart)
  python scripts/catalogue_agency_agents.py <clone d'agency-agents> --liste     la liste en Markdown (pour la PR)

Le script lit chaque agent au commit épinglé (`git show COMMIT:chemin`, quel que soit l'état du clone), le range par
catégorie dans `atelier/gabarits/catalogue/<catégorie>/<id>.md` et réécrit tout le catalogue : même commit, même
résultat. L'en-tête d'un modèle garde son nom, sa description et sa source (licence MIT, `LICENCE-agency-agents.txt`).

Le corps est le texte de l'agent, en anglais, raccourci pour que les consignes entières (socle `_catalogue.md`, les
garde-fous, puis ce corps) tiennent dans les 8 000 caractères de Config : sans les blocs de code, les emojis ni les
tirets longs ; d'abord l'introduction, l'identité, les règles, la mission, puis le reste tant qu'il y a la place.

Les garde-fous (`_securite.md`, `_sante.md`, `_juridique.md`) passent avant le rôle. Les agents de sécurité passent la
règle défensive de Julien ; ceux qui la dépassaient sont adaptés ici, phrase par phrase (ADAPTATIONS) : une phrase
qui ne se retrouve pas dans la source arrête le script.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from noyau.typographie import sans_artefacts  # noqa: E402

DEPOT = "https://github.com/msitarzewski/agency-agents"
COMMIT = "8ae6164602c95ca78828b148b9052460ee426885"  # lu le 20.11.2026
CATEGORIES = ("academic", "design", "engineering", "finance", "game-development", "gis", "healthcare", "marketing",
              "paid-media", "product", "project-management", "research", "sales", "security", "spatial-computing",
              "specialized", "support", "testing")
SORTIE = RACINE / "atelier" / "gabarits" / "catalogue"
MAXIMUM = 8000  # Config.consignes
TON = "professional, clear and precise, formal address"

# Les garde-fous, au-dessus du rôle. Sécurité : toute la catégorie. Santé : aussi refusé pour la zone États-Unis
# (le 144 et le 145 sont suisses).
SANTE = {"healthcare-clinical-evidence-agent", "healthcare-innovation-strategist",
         "healthcare-sovereign-health-systems-agent", "healthcare-aging-parent-care-companion",
         "healthcare-customer-service", "healthcare-marketing-compliance", "medical-billing-coding-specialist"}
JURIDIQUE = {"legal-billing-time-tracking", "legal-client-intake", "legal-document-review",
             "support-legal-compliance-checker", "data-privacy-officer", "healthcare-marketing-compliance",
             "finance-tax-strategist", "study-abroad-advisor"}

PENTEST = """You are **Penetration Test Coordinator**, the person who helps a company commission, frame and follow up penetration tests of its own systems, carried out by an authorized provider under a written contract. You never run an attack yourself: you help define the scope, check the authorization, read the report, prioritize the fixes and plan the retest.

## Your Identity & Memory

- **Role**: Coordinator of authorized penetration tests on systems the company owns, from scoping to retest
- **Personality**: Methodical, precise, calm. You turn a technical report into decisions the company can act on
- **Experience**: You know the testing standards (PTES, OWASP Testing Guide, NIST SP 800-115) well enough to frame an engagement and to judge whether a report is complete

## Critical Rules You Must Follow

- Every system in scope belongs to the company, and the provider holds a written authorization that names it
- You never perform reconnaissance, scanning, exploitation, phishing or any other attack, and you never help someone do it
- Stop and alert the company if a report shows signs of an active breach by a real attacker
- Protect any sensitive data that appears in a report: share only what the fix needs

## Scoping & Rules of Engagement

- Define the scope explicitly: IP ranges, domains, cloud accounts and applications that the company owns
- Establish rules of engagement: testing windows, off-limits systems, escalation procedures, emergency contacts
- Agree on communication channels: how critical findings are reported immediately versus in the final report

## Reading the Report & Remediation

- Check that each finding is classified by severity and business impact, not just CVSS score
- Turn every finding into a specific remediation with an owner and a deadline: "patch the vulnerability" is not a recommendation
- Make sure the executive summary is understandable by non-technical stakeholders
- Plan a retest so the company can verify its fixes

## Your Success Metrics

- Zero scope violations: every tested system is owned by the company and covered by the authorization
- Every finding has an owner, a fix and a retest result
- Client remediation success rate exceeds 90% on retest"""

# Les agents de sécurité qui dépassaient la règle défensive : chaque ligne (repérée par un extrait de la source) est
# remplacée par sa version défensive, ou retirée (None) ; une sous-section (### titre) peut être retirée entière.
ADAPTATIONS: dict[str, dict] = {
    "security-penetration-tester": {
        "titre": "Penetration Test Coordinator",
        "description": "Defensive coordinator for penetration tests of the company's own systems: scoping, written "
                       "authorization, report reading, remediation and retest. Never runs an attack itself.",
        "corps": PENTEST,
        "adapte": "réécrit en coordination défensive (cadrage, autorisation écrite, lecture du rapport, corrections, "
                  "contre-test) ; reconnaissance, exploitation, pivot et ingénierie sociale retirés",
    },
    "security-blockchain-security-auditor": {
        "lignes": {
            "reproduced dozens of real-world exploits": "You are **Blockchain Security Auditor**, a relentless smart contract security researcher who assumes every contract is vulnerable until proven otherwise. You have dissected hundreds of protocols and written audit reports that have prevented millions in losses. Your job is not to make developers feel good, it is to find the bug before the attacker does.",
            "Every finding must include a proof-of-concept exploit": "- **Default requirement**: Every finding must include a concrete attack scenario with estimated impact, a fix, and a regression test that runs against the company's own code in a local test environment",
            "Provide proof-of-concept exploits solely": "- Never write exploit code usable against a deployed contract: describe the scenario, the fix and the regression test",
            "include a reproducible proof of concept": "- 100% of findings include a concrete attack scenario and a regression test that proves the fix",
        },
        "sections": ("Foundry Exploit Proof-of-Concept",),
        "adapte": "plus de code d'exploitation : chaque faille a un scénario, une correction et un test de non-régression local",
    },
    "security-architect": {
        "lignes": {"proof of exploitability": "- **Hard rule**: Every finding must include a severity rating, a description of how it could be abused, and concrete remediation with code"},
        "adapte": "la preuve d'exploitation devient la description de l'abus possible",
    },
    "security-appsec-engineer": {
        "lignes": {
            "developers exploit and fix real vulnerabilities": "- Run hands-on workshops where developers find and fix vulnerabilities in deliberately vulnerable training applications",
            "Execute manual penetration testing": "- Commission an authorized penetration test of high-risk features from a provider before production release",
        },
        "adapte": "ateliers sur des applications d'entraînement ; le test d'intrusion est commandé à un prestataire",
    },
    "security-cloud-security-architect": {
        "lignes": {"Run penetration tests and red team exercises": "- Commission authorized penetration tests of the company's cloud environment from a provider, and track the fixes"},
        "adapte": "les tests d'intrusion et la red team sont commandés à un prestataire",
    },
    "security-threat-detection-engineer": {
        "lignes": {
            "running atomic red team tests or purple team exercises": "- Validate that detections actually fire by replaying recorded logs and public test datasets in a test environment",
            "Validate detections quarterly with purple team exercises": "- Revalidate detections quarterly against fresh recorded logs: a rule that passed testing 12 months ago may not catch today's variant",
            "Align detection roadmap with purple team": "- Align detection roadmap with incident post-mortem action items and threat intelligence",
            "Run atomic red team tests or manual simulations": "- Replay recorded logs or public test datasets to confirm the detection fires on the targeted technique",
        },
        "sections": ("Purple Team Integration",),
        "adapte": "les détections se valident sur des journaux enregistrés et des jeux de données publics, plus par des attaques simulées",
    },
    "security-threat-intelligence-analyst": {
        "lignes": {
            "and the underground marketplaces where stolen data is traded": "- **Memory**: You maintain a mental map of the threat landscape: which APT groups target which industries, what tools they favor, how their infrastructure is set up, and how their TTPs evolve across campaigns. You follow ransomware ecosystems and initial access brokers through published intelligence",
            "informed red team exercises and purple team":"- **Experience**: You have produced tactical intelligence that fed detection rules catching active intrusions, operational intelligence that informed defensive improvements, and strategic intelligence that shaped board-level risk decisions. You have written intelligence on state-sponsored groups, financially motivated crime syndicates, and hacktivists alike",
            "dark web forums, paste sites, and underground marketplaces": "- Monitor threat feeds and reputable intelligence services for emerging threats, leaked credentials of the company, and indicators of compromise",
            "Analyze malware samples to extract IOCs": "- Read published malware analysis reports to extract IOCs, understand capabilities, and identify connections to known threat actors",
            "known malware samples and attack simulations": "- Validate detection rules against recorded logs and public test datasets before deployment",
            "OSINT, dark web monitoring, ISAC sharing": "- Establish collection sources: commercial threat feeds, ISAC sharing, government advisories, reputable leak monitoring services",
            "malware sample retrieval, infrastructure scanning": "- Configure automated collection: feed ingestion and the company's own telemetry",
        },
        "sections": ("Advanced Malware Analysis", "Infrastructure Intelligence"),
        "adapte": "plus de forums clandestins, d'échantillons de logiciels malveillants ni de balayage d'infrastructures tierces : des sources reconnues et la télémétrie du client",
    },
}
# Ce qui ne doit plus rester dans le texte d'un agent de sécurité, une fois adapté et raccourci.
INTERDITS_SECURITE = re.compile(r"red team|purple team|proof.of.concept|proof of exploitability|underground|dark web|"
                                r"malware sample|infrastructure scanning|atomic test|weaponized doc|social engineering", re.I)

EMOJIS = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿⏩-⏺️‍⃣]")
PRIORITES = ((r"identity|who you are|role definition|persona", 1),
             (r"learning|memory", 99),
             (r"rule|guardrail|boundar|ethic|constraint|non.negotiable|never|safety|limit", 2),
             (r"mission|capabilit|competenc|skill|expertise|responsibilit|what you do", 3),
             (r"communication|style|tone|voice", 4),
             (r"workflow|process|method|approach|framework|how you work|decision", 5),
             (r"success|metric|kpi", 6))


def git(clone: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(clone), *args], check=True, capture_output=True, text=True).stdout


def agents(clone: Path) -> list[tuple[str, str]]:
    """(catégorie, chemin) des agents au commit épinglé : les fichiers .md des catégories, sans les README."""
    chemins = git(clone, "ls-tree", "-r", "--name-only", COMMIT).splitlines()
    return sorted((c.split("/")[0], c) for c in chemins
                  if c.split("/")[0] in CATEGORIES and c.endswith(".md") and not Path(c).name.startswith("README"))


def adapter(ident: str, texte: str) -> str:
    """Les lignes et sous-sections de sécurité remplacées (ADAPTATIONS) ; chaque extrait doit se trouver une fois."""
    a = ADAPTATIONS.get(ident, {})
    lignes = texte.split("\n")
    for extrait, nouvelle in a.get("lignes", {}).items():
        trouvees = [i for i, l in enumerate(lignes) if extrait in l]
        if len(trouvees) != 1:
            raise SystemExit(f"{ident} : « {extrait} » trouvé {len(trouvees)} fois (une attendue)")
        lignes[trouvees[0]] = nouvelle
    for titre in a.get("sections", ()):
        debut = [i for i, l in enumerate(lignes) if re.fullmatch(rf"#+ .*{re.escape(titre)}\s*", l)]
        if len(debut) != 1:
            raise SystemExit(f"{ident} : la section « {titre} » trouvée {len(debut)} fois (une attendue)")
        niveau = len(lignes[debut[0]]) - len(lignes[debut[0]].lstrip("#"))
        fin = next((j for j in range(debut[0] + 1, len(lignes))
                    if re.match(rf"#{{1,{niveau}}} ", lignes[j])), len(lignes))
        del lignes[debut[0]:fin]
    return "\n".join(lignes)


def nettoyer(texte: str) -> str:
    """Sans blocs de code, commentaires, emojis, filets ni tirets longs ; les titres restés vides partent."""
    texte = re.sub(r"<!--.*?-->", "", texte, flags=re.S)
    lignes, code = [], False
    for l in texte.split("\n"):
        if re.match(r"\s*(```|~~~)", l):
            code = not code
            continue
        if not code and not re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", l):
            lignes.append(l)
    texte = sans_artefacts(EMOJIS.sub("", "\n".join(lignes)))
    lignes = [re.sub(r"^(#+)\s+", r"\1 ", l.rstrip()) for l in texte.split("\n")]
    while True:  # un titre suivi d'un titre de même niveau ou plus haut, ou de la fin, n'a plus de contenu
        pleines = [i for i, l in enumerate(lignes) if l.strip()]
        vides = set()
        for k, i in enumerate(pleines):
            m = re.match(r"(#+) ", lignes[i])
            suite = lignes[pleines[k + 1]] if k + 1 < len(pleines) else None
            if m and (suite is None or (re.match(r"#+ ", suite) and len(re.match(r"#+", suite).group()) <= len(m.group(1)))):
                vides.add(i)
        if not vides:
            break
        lignes = [l for i, l in enumerate(lignes) if i not in vides]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lignes)).strip()


def priorite(titre: str) -> int:
    return next((p for motif, p in PRIORITES if re.search(motif, titre, re.I)), 7)


def couper(texte: str, limite: int) -> str:
    """Le début d'une section qui tient dans la limite, coupé entre deux lignes, sans finir sur un titre."""
    garde, n = [], 0
    for l in texte.split("\n"):
        if n + len(l) + 1 > limite:
            break
        garde.append(l)
        n += len(l) + 1
    while garde and (not garde[-1].strip() or garde[-1].startswith("#")):
        garde.pop()
    return "\n".join(garde) if sum(1 for l in garde if l.strip() and not l.startswith("#")) >= 2 else ""


def raccourcir(corps: str, budget: int) -> str:
    """L'introduction et les sections (## titre) par ordre d'importance, tant qu'elles tiennent ; dans l'ordre d'origine."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for l in corps.split("\n"):
        if l.startswith("# "):
            continue  # le titre de l'agent, déjà dans l'en-tête
        if l.startswith("## "):
            sections.append((l, []))
        else:
            sections[-1][1].append(l)
    textes = [(t, "\n".join(c).strip()) for t, c in sections]
    choix: dict[int, str] = {}
    reste = budget
    for i, (t, c) in sorted(enumerate(textes), key=lambda e: (priorite(e[1][0]) if e[0] else 0, e[0])):
        if not c or (t and priorite(t) == 99):
            continue
        texte = f"{t}\n\n{c}" if t else c
        if len(texte) + 2 <= reste:
            choix[i] = texte
        elif (not t or priorite(t) <= 3) and reste > 400:
            choix[i] = couper(texte, reste - 2)
        else:
            continue
        reste -= len(choix[i]) + 2
    return "\n\n".join(choix[i] for i in sorted(choix) if choix[i])


def lire_socle(nom: str) -> str:
    return (SORTIE / nom).read_text(encoding="utf-8").strip()


def convertir(clone: Path, categorie: str, chemin: str) -> tuple[str, str, dict]:
    """(id, contenu du fichier, résumé pour la liste) d'un agent."""
    ident = Path(chemin).stem
    brut = git(clone, "show", f"{COMMIT}:{chemin}").replace("\r\n", "\n")
    _, entete_source, corps = brut.split("---", 2)
    source = yaml.safe_load(entete_source)
    a = ADAPTATIONS.get(ident, {})
    garde_fous = [g for g, oui in (("securite", categorie == "security"), ("sante", ident in SANTE),
                                   ("juridique", ident in JURIDIQUE)) if oui]
    fixe = "\n\n".join([lire_socle("_catalogue.md"), *(lire_socle(f"_{g}.md") for g in garde_fous)])
    corps = nettoyer(a["corps"] if "corps" in a else adapter(ident, corps))
    corps = raccourcir(corps, MAXIMUM - len(fixe) - 2)
    if categorie == "security" and (m := INTERDITS_SECURITE.search(corps)):
        raise SystemExit(f"{ident} : « {m.group()} » reste dans le texte d'un agent de sécurité")
    un = lambda v: sans_artefacts(EMOJIS.sub("", " ".join(str(v).split())))  # noqa: E731
    entete = {"titre": un(a.get("titre", source["name"])), "description": un(a.get("description", source["description"])),
              "metier": "general", "categorie": categorie, "ton": TON, "garde_fous": garde_fous,
              "source": {"depot": DEPOT, "chemins": [chemin], "commit": COMMIT, "licence": "MIT"}}
    if "adapte" in a:
        entete["adapte"] = a["adapte"]
    contenu = "---\n" + yaml.safe_dump(entete, allow_unicode=True, sort_keys=False, width=10**6,
                                       default_flow_style=None) + "---\n" + corps + "\n"
    return ident, contenu, {"id": ident, "titre": entete["titre"], "categorie": categorie, "garde_fous": garde_fous,
                            "adapte": a.get("adapte"), "taille": len(fixe) + 2 + len(corps)}


def liste(resumes: list[dict]) -> str:
    lignes = [f"{len(resumes)} modèles installés (commit `{COMMIT[:7]}`), aucun écarté.", ""]
    for categorie in CATEGORIES:
        du = [r for r in resumes if r["categorie"] == categorie]
        lignes += [f"<details><summary><b>{categorie}</b> : {len(du)}</summary>", ""]
        for r in du:
            notes = [g for g in r["garde_fous"]] + (["adapté : " + r["adapte"]] if r["adapte"] else [])
            lignes.append(f"- `{r['id']}` {r['titre']}" + (f" ({' ; '.join(notes)})" if notes else ""))
        lignes += ["", "</details>"]
    return "\n".join(lignes)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("clone", type=Path)
    p.add_argument("--verifier", action="store_true")
    p.add_argument("--liste", action="store_true")
    args = p.parse_args()
    fichiers, resumes = {}, []
    for categorie, chemin in agents(args.clone):
        ident, contenu, resume = convertir(args.clone, categorie, chemin)
        if any(ident == Path(f).stem for f in fichiers):
            raise SystemExit(f"{ident} : deux agents portent ce nom")
        fichiers[f"{categorie}/{ident}.md"] = contenu
        resumes.append(resume)
    if args.liste:
        print(liste(resumes))
        return 0
    existants = {str(f.relative_to(SORTIE)) for f in SORTIE.glob("*/*.md")}
    ecarts = sorted({f for f in fichiers if not (SORTIE / f).is_file() or (SORTIE / f).read_text(encoding="utf-8") != fichiers[f]}
                    | (existants - set(fichiers)))
    if args.verifier:
        print("\n".join(ecarts) or f"{len(fichiers)} modèles, aucun écart")
        return 1 if ecarts else 0
    for f in existants - set(fichiers):
        (SORTIE / f).unlink()
    for f, contenu in fichiers.items():
        (SORTIE / f).parent.mkdir(parents=True, exist_ok=True)
        (SORTIE / f).write_text(contenu, encoding="utf-8")
    print(f"{len(fichiers)} modèles écrits ({len(ecarts)} changés)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
