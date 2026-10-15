#!/usr/bin/env python3
"""Hub : sert la page home et une API de lecture de /workspace (projets, arbre, git, notes .md)."""
import json, os, re, subprocess, mimetypes
from collections import Counter
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

RACINE = os.path.realpath(os.environ.get("WORKSPACE", "/workspace"))
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
EXCLUS_PROJETS = {"hers"}
IGNORES = {".git", "node_modules", ".corbeille", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".liens.json", ".liens-cours.json", ".agenda.json"}
MAX_NOEUDS = 400
MAX_PROFONDEUR = 5


def sous(base, rel):
    """Chemin absolu de rel sous base, ou None si ça sort de base."""
    p = os.path.realpath(os.path.join(base, rel))
    return p if p == base or p.startswith(base + os.sep) else None


def dossier_projet(nom):
    if not nom or "/" in nom or nom.startswith("."):
        return None
    p = sous(RACINE, nom)
    return p if p and os.path.isdir(p) else None


def git(chemin, *args):
    try:
        r = subprocess.run(["git", "-C", chemin, *args], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def infos_git(chemin):
    if not os.path.isdir(os.path.join(chemin, ".git")):
        return None
    log = git(chemin, "log", "-8", "--pretty=%h|%an|%ad|%s", "--date=short") or ""
    commits = [dict(zip(("hash", "auteur", "date", "message"), l.split("|", 3))) for l in log.splitlines()]
    remote = git(chemin, "remote", "get-url", "origin") or ""
    if remote.startswith("git@github.com:"):
        remote = "https://github.com/" + remote[15:]
    if remote.endswith(".git"):
        remote = remote[:-4]
    modifs = (git(chemin, "status", "--porcelain") or "").splitlines()
    return {"branche": git(chemin, "rev-parse", "--abbrev-ref", "HEAD"), "remote": remote,
            "modifies": len(modifs), "commits": commits}


def description(chemin):
    for n in os.listdir(chemin):
        if n.lower().startswith("readme") and n.lower().endswith((".md", ".txt")):
            try:
                with open(os.path.join(chemin, n), encoding="utf-8", errors="replace") as f:
                    for l in f:
                        l = l.strip().lstrip("#").strip()
                        if l:
                            return l[:200]
            except OSError:
                pass
    return ""


def arbre(chemin, profondeur=0, compteur=None):
    compteur = compteur if compteur is not None else [0]
    noeuds = []
    try:
        entrees = sorted(os.scandir(chemin), key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))
    except OSError:
        return noeuds
    for e in entrees:
        if e.name in IGNORES:
            continue
        if compteur[0] >= MAX_NOEUDS:
            noeuds.append({"nom": "…", "type": "plus"})
            break
        compteur[0] += 1
        if e.is_dir(follow_symlinks=False):
            n = {"nom": e.name, "type": "dossier"}
            if profondeur < MAX_PROFONDEUR:
                n["enfants"] = arbre(e.path, profondeur + 1, compteur)
            noeuds.append(n)
        else:
            noeuds.append({"nom": e.name, "type": "fichier"})
    return noeuds


def stats(chemin):
    fichiers = dossiers = taille = 0
    ext = Counter()
    for r, ds, fs in os.walk(chemin):
        ds[:] = [d for d in ds if d not in IGNORES]
        dossiers += len(ds)
        for f in fs:
            fichiers += 1
            try:
                taille += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
            ext[os.path.splitext(f)[1].lower() or "(sans)"] += 1
    return {"fichiers": fichiers, "dossiers": dossiers, "taille": taille, "extensions": ext.most_common(6)}


def notes(chemin):
    res = []
    for r, ds, fs in os.walk(chemin):
        ds[:] = [d for d in ds if d not in IGNORES]
        for f in fs:
            if f.lower().endswith(".md"):
                res.append(os.path.relpath(os.path.join(r, f), chemin))
    return sorted(res, key=lambda p: (p.count("/"), p.lower()))[:200]


def resume_projet(nom):
    p = dossier_projet(nom)
    g = infos_git(p)
    return {"nom": nom, "description": description(p),
            "branche": g and g["branche"], "dernier": g and g["commits"] and g["commits"][0]["date"],
            "modifies": g and g["modifies"]}


FICHIER_LIENS_COURS = os.path.join(RACINE, "hers", ".liens-cours.json")


def lire_json(p, defaut):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def ecrire_json(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


FICHIER_AGENDA = os.path.join(RACINE, "hers", ".agenda.json")
TYPES_AGENDA = {"devoir", "test", "examen", "autre"}


def nettoyer_agenda(l):
    """Valide la liste envoyée par la page (devoirs, tests...) ; lève une exception si invalide."""
    res = []
    for x in l[:2000]:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(x["date"])) or not str(x["titre"]).strip():
            raise ValueError
        res.append({"id": str(x["id"])[:40], "titre": str(x["titre"]).strip()[:120], "date": x["date"],
                    "type": x.get("type") if x.get("type") in TYPES_AGENDA else "autre",
                    "cours": str(x.get("cours") or "")[:40], "fait": bool(x.get("fait"))})
    return res


def cours_valide(nom):
    return bool(nom) and "/" not in nom and not nom.startswith(".") and os.path.isdir(os.path.join(RACINE, "hers", nom))


def lire_liens(cours=None):
    if cours is None:
        return lire_json(os.path.join(RACINE, "hers", ".liens.json"), [])
    return lire_json(FICHIER_LIENS_COURS, {}).get(cours, [])


def liste_projets():
    noms = sorted(n for n in os.listdir(RACINE)
                  if not n.startswith(".") and n not in EXCLUS_PROJETS and os.path.isdir(os.path.join(RACINE, n)))
    return [resume_projet(n) for n in noms]


def detail_projet(nom):
    p = dossier_projet(nom)
    return {"nom": nom, "description": description(p), "git": infos_git(p), "stats": stats(p),
            "arbre": arbre(p), "notes": notes(p)}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def chemin_note(self, nom, rel):
        p = dossier_projet(nom)
        if not p or not rel.lower().endswith(".md"):
            return None
        return sous(p, rel)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/api/projets":
            return self.json(liste_projets())
        if u.path == "/api/hers":
            return self.json(detail_projet("hers") if dossier_projet("hers") else {"erreur": "absent"})
        if u.path == "/api/projet":
            if not dossier_projet(q.get("nom")) or q.get("nom") in EXCLUS_PROJETS:
                return self.json({"erreur": "introuvable"}, 404)
            return self.json(detail_projet(q["nom"]))
        if u.path == "/api/note":
            p = self.chemin_note(q.get("nom"), q.get("chemin", ""))
            if not p or not os.path.isfile(p):
                return self.json({"erreur": "introuvable"}, 404)
            with open(p, encoding="utf-8", errors="replace") as f:
                return self.json({"contenu": f.read()})
        if u.path == "/api/liens":
            cours = q.get("cours")
            if cours is not None and not cours_valide(cours):
                return self.json({"erreur": "introuvable"}, 404)
            return self.json(lire_liens(cours))
        if u.path == "/api/agenda":
            return self.json(lire_json(FICHIER_AGENDA, []))
        if u.path == "/api/fichier":
            p = dossier_projet(q.get("nom"))
            p = p and sous(p, q.get("chemin", ""))
            if not p or not os.path.isfile(p) or os.sep + ".git" + os.sep in p:
                return self.json({"erreur": "introuvable"}, 404)
            with open(p, "rb") as f:
                b = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(p)[0] or "application/octet-stream")
            self.send_header("Content-Disposition", ("attachment" if q.get("dl") else "inline") + "; filename*=UTF-8''" + quote(os.path.basename(p)))
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        rel = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
        p = sous(STATIC, rel)
        if not p or not os.path.isfile(p):
            return self.json({"erreur": "introuvable"}, 404)
        with open(p, "rb") as f:
            b = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(p)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_PUT(self):
        u = urlparse(self.path)
        if u.path == "/api/liens":
            try:
                l = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                l = [{"titre": str(x["titre"])[:80], "url": str(x["url"])[:500]} for x in l
                     if str(x["url"]).startswith(("http://", "https://", "file:"))]
                cours = parse_qs(u.query).get("cours", [None])[0]
                if cours is None:
                    ecrire_json(os.path.join(RACINE, "hers", ".liens.json"), l)
                else:
                    if not cours_valide(cours):
                        raise ValueError
                    tous = lire_json(FICHIER_LIENS_COURS, {})
                    tous[cours] = l
                    ecrire_json(FICHIER_LIENS_COURS, tous)
                return self.json({"ok": True})
            except Exception:
                return self.json({"erreur": "requete invalide"}, 400)
        if u.path == "/api/agenda":
            try:
                l = nettoyer_agenda(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))))
                ecrire_json(FICHIER_AGENDA, l)
                return self.json({"ok": True})
            except Exception:
                return self.json({"erreur": "requete invalide"}, 400)
        if u.path != "/api/note":
            return self.json({"erreur": "introuvable"}, 404)
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            nom = d["nom"]
            if nom in EXCLUS_PROJETS and nom != "hers":
                raise ValueError
            p = self.chemin_note(nom, d["chemin"])
            if not p or os.sep + ".git" + os.sep in p:
                raise ValueError
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(d["contenu"])
            os.chmod(p, 0o664)
            self.json({"ok": True})
        except Exception:
            self.json({"erreur": "requete invalide"}, 400)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 80), H).serve_forever()
