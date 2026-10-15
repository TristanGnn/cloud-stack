# Cloud Stack : fiche technique

Un espace de travail personnel accessible depuis n'importe quel navigateur : un hub d'accueil, un éditeur de code, un gestionnaire de fichiers, un terminal et un IDE pédagogique. Tout tourne sur **une seule machine**, dans **une seule pile Docker Compose**, sans aucun port ouvert sur Internet.

---

## 1. Vue d'ensemble

```
                    Navigateur (PC, tablette, téléphone)
                                  │  HTTPS
                                  ▼
          ┌──────────────────────────────────────────────┐
          │                 CLOUDFLARE                    │
          │                                               │
          │   ① Cloudflare Access  (login obligatoire)    │
          │          │  seul l'email autorisé passe       │
          │          ▼                                    │
          │   ② Tunnel  (routage par sous-domaine)        │
          └──────────────────────┬───────────────────────┘
                                 │  connexion SORTANTE
                                 │  (initiée par la machine)
   ┌─────────────────────────────┼──────────────────────────────────┐
   │  MACHINE  (Docker Compose)  ▼                                  │
   │                      ┌─────────────┐                           │
   │                      │ cloudflared │                           │
   │                      └──────┬──────┘                           │
   │      ┌──────────┬───────────┼───────────┬────────────┐         │
   │      ▼          ▼           ▼           ▼            ▼         │
   │  ┌───────┐  ┌───────┐  ┌─────────┐  ┌──────────┐  ┌─────────┐  │
   │  │ home  │  │ code  │  │  cloud  │  │ terminal │  │pseudoide│  │
   │  │ :80   │  │ :8443 │  │  :80    │  │  :7681   │  │  :8765  │  │
   │  └───┬───┘  └───┬───┘  └──┬───┬──┘  └────┬─────┘  └────┬────┘  │
   │      │          │         │   │          │             │       │
   │      │          │         │ ┌─▼──┐       │             │       │
   │      │          │         │ │ db │ MariaDB             │       │
   │      │          │         │ └────┘                     │       │
   │      ▼          ▼         ▼                ▼            ▼       │
   │   ══════════════ /srv/workspace  (monté en /workspace) ═══════  │
   │                  racine de fichiers commune à tout              │
   └─────────────────────────────────────────────────────────────────┘
```

**Idée clé** : tous les services voient **le même dossier** (`/srv/workspace` sur la machine, `/workspace` dans les conteneurs). Un fichier créé dans le terminal apparaît aussitôt dans l'éditeur et dans Nextcloud.

---

## 2. Les services

| Service | Sous-domaine | Image | Rôle |
|---|---|---|---|
| `home` | `home.<domaine>` | **fait maison** (`hub/`) | Page d'accueil : espace **Build** (projets, notes, git) et **Hers** (cours, liens, agenda) |
| `code` | `code.<domaine>` | `lscr.io/linuxserver/code-server` | VS Code dans le navigateur |
| `cloud` | `cloud.<domaine>` | `nextcloud:apache` | Gestion de fichiers (upload, partage, aperçu) |
| `db` | *(interne)* | `mariadb:11` | Base de données de Nextcloud |
| `terminal` | `term.<domaine>` | **fait maison** (`terminal/`) | Shell bash dans le navigateur (ttyd + gcc, Java, outils réseau) |
| `pseudoide` | `ide.<domaine>` | `python:3.12-alpine` | Lance le repo pseudoIDE (dans `/workspace/pseudoIDE`) |
| `cloudflared` | *(interne)* | `cloudflare/cloudflared` | Relie la machine à Cloudflare (le tunnel) |

### Arborescence du projet

```
cloud-stack/
├── docker-compose.yml     ← définit les 7 services
├── .env                   ← SECRETS (jamais partagé, jamais commité)
├── hub/                   ← service « home »
│   ├── Dockerfile         (python:3.12-alpine + git)
│   ├── serveur.py         (serveur HTTP + API JSON, stdlib uniquement)
│   └── static/index.html  (interface, une seule page)
└── terminal/              ← service « terminal »
    ├── Dockerfile         (ubuntu 24.04 + ttyd + outils)
    └── demarrer.sh        (ouvre le shell dans le bon dossier)
```

Le reste (code-server, Nextcloud, MariaDB, cloudflared) est **téléchargé automatiquement** au premier lancement.

### Données persistantes

| Où | Contenu | Perte si supprimé |
|---|---|---|
| `/srv/workspace` (dossier hôte) | **Tous tes fichiers** | ❌ Tout |
| volume `nextcloud-data` | Config + comptes Nextcloud | Comptes et partages Nextcloud |
| volume `db-data` | Base MariaDB | Idem (Nextcloud inutilisable) |
| volume `code-config` | Extensions/réglages VS Code | Juste les extensions |

> À sauvegarder en priorité : `/srv/workspace` et le `.env`.

---

## 3. Sécurité

### Le modèle : 3 couches

```
  Internet ──►  ① Cloudflare Access  ──►  ② Tunnel  ──►  ③ Login propre au service
               (qui es-tu ?)             (aucun port      (code-server, Nextcloud)
                                          ouvert)
```

**① Cloudflare Access : le vrai verrou.**
Chaque sous-domaine (`*.<domaine>`) est protégé par une application Access. Avant même d'atteindre la machine, il faut se connecter. Seul l'email autorisé passe (login via compte Cloudflare + code par email en secours). Une requête non authentifiée reçoit une redirection `302` vers la page de login Cloudflare.

**② Le tunnel : aucune porte ouverte.**
`cloudflared` établit une connexion **sortante** vers Cloudflare. Le routeur/box n'a **aucun port ouvert**, la machine n'a **aucun port publié** (pas de `ports:` dans le compose). Impossible de contacter un service sans passer par Cloudflare.

**③ Logins internes.**
code-server a un mot de passe (`CODE_PASSWORD`), Nextcloud a ses comptes. Le hub, le terminal et pseudoIDE n'en ont **pas** : ils reposent entièrement sur Access.

### Mesures en place

- ✅ Conteneurs `home`, `pseudoide`, `terminal` lancés en **utilisateur non-root** (uid 1000).
- ✅ Secrets dans `.env`, pas dans le code.
- ✅ Hub : chemins vérifiés (impossible de sortir de `/workspace` avec `../`), agenda/liens validés côté serveur.
- ✅ Terminal : le paramètre `?arg=` n'accepte qu'un nom de dossier simple (pas de `/`, pas de `.`).
- ✅ pseudoIDE : n'accepte que l'hôte `ide.<domaine>` (`--hotes-autorises`).
- ✅ Nextcloud : HTTPS forcé, domaine de confiance restreint.

### Limites à connaître (honnêtement)

| Risque | Pourquoi | Atténuation |
|---|---|---|
| **Compte Cloudflare = clé de tout** | Qui contrôle le compte contrôle Access et les routes | 2FA forte sur le compte Cloudflare **et** sur l'email |
| Terminal / hub sans mot de passe | Si Access est mal configuré, ils sont ouverts | Toujours **tester de l'extérieur** (§4, étape 7) |
| Un service compromis voit tout `/workspace` | Tous montent le même dossier en écriture | Ne pas mettre de clés SSH, tokens, etc. dans `/srv/workspace` |
| Cloudflare voit le trafic en clair | Le TLS est terminé chez Cloudflare | Accepté ; ne pas y faire transiter de données ultra sensibles |
| `sudo` dans code-server | `SUDO_PASSWORD` donne root **dans le conteneur** | Mot de passe fort, différent des autres |
| Images en `:latest` | Une mise à jour peut casser quelque chose | Sauvegarder avant `docker compose pull` |

> **Règle d'or** : créer la règle Access **AVANT** d'activer le tunnel, puis vérifier.

---

## 4. Protocole d'installation

### Prérequis

| | Minimum | Conseillé |
|---|---|---|
| Machine | Linux 64 bits allumée 24/7 (PC, mini-PC, VPS) | Ubuntu Server 24.04 |
| CPU / RAM | 2 cœurs / 4 Go | 4 cœurs / 8 Go |
| Disque | 20 Go libres | SSD + disque séparé pour `/srv/workspace` |
| Logiciels | Docker Engine + plugin `docker compose` | |
| Réseau | Accès Internet sortant (aucun port à ouvrir) | |
| Comptes | **Nom de domaine** + compte **Cloudflare** (plan Free) | 2FA activée partout |

### Étapes

**1. Domaine sur Cloudflare**
Ajouter le domaine dans Cloudflare (plan Free), puis chez le registrar remplacer les serveurs DNS par les 2 nameservers donnés par Cloudflare. Attendre l'email de confirmation (quelques minutes à 24 h).

**2. Dossier de travail**
```bash
sudo mkdir -p /srv/workspace
sudo chown $USER:$USER /srv/workspace
```
> Le compose suppose l'uid **1000**. Vérifier avec `id -u` ; sinon adapter `user:` / `PUID` / `PGID`.

**3. Récupérer la pile et créer le `.env`**
```bash
cd ~/cloud-stack
cp .env.example .env
nano .env
```
```ini
DOMAIN=mondomaine.com
CODE_PASSWORD=          # mot de passe long et unique
SUDO_PASSWORD=          # différent du précédent
DB_PASSWORD=            # ⚠ ne plus jamais le changer après le 1er lancement
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ADMIN_PASSWORD=
TUNNEL_TOKEN=           # rempli à l'étape 5
```
Générer des mots de passe : `openssl rand -base64 24`

**4. Cloudflare Access (AVANT le tunnel)**
Zero Trust → *Access* → *Applications* → *Add* → *Self-hosted*
- Domaine : `*.mondomaine.com`
- Politique : *Allow*, *Emails* = ton adresse uniquement
- Méthode de login : One-time PIN (et/ou autre fournisseur)
- Durée de session : 24 h à 1 semaine

**5. Créer le tunnel**
Zero Trust → *Networks* → *Tunnels* → *Create* (type Cloudflared). Copier le **token** dans `TUNNEL_TOKEN`, puis ajouter les routes (*Public hostnames*) :

| Sous-domaine | Service |
|---|---|
| `home` | `http://home:80` |
| `code` | `http://code:8443` |
| `cloud` | `http://cloud:80` |
| `term` | `http://terminal:7681` |
| `ide` | `http://pseudoide:8765` |

**6. Lancer**
```bash
docker compose up -d --build
docker compose ps          # tout doit être "running"
docker compose logs -f cloudflared   # attendre "Registered tunnel connection"
```

**7. Vérifier la sécurité (indispensable)**
Depuis un réseau extérieur (4G) ou en navigation privée :
```bash
for s in home code cloud term ide; do
  curl -s -o /dev/null -w "$s → %{http_code} %{redirect_url}\n" https://$s.mondomaine.com
done
```
Chaque ligne doit afficher **`302`** vers `…cloudflareaccess.com`. Si un service répond `200` sans login → **couper le tunnel** (`docker compose stop cloudflared`) et corriger Access.

**8. Nextcloud : voir `/workspace`**
```bash
docker compose exec -u www-data cloud php occ app:enable files_external
docker compose exec -u www-data cloud php occ files_external:create Workspace local null::null -c datadir=/workspace
docker compose exec -u www-data cloud php occ files_external:option 1 filesystem_check_changes 1
docker compose exec -u www-data cloud php occ files:scan --all
```
Donner les droits d'écriture à Nextcloud (uid 33) sans casser les tiens :
```bash
sudo setfacl -R -m u:33:rwX,d:u:33:rwX -m u:1000:rwX,d:u:1000:rwX /srv/workspace
```

---

## 5. Exploitation

| Action | Commande |
|---|---|
| État | `docker compose ps` |
| Logs d'un service | `docker compose logs -f <service>` |
| Redémarrer un service | `docker compose restart <service>` |
| Appliquer une modif du hub | `docker compose up -d --build home` |
| Appliquer une modif du `.env` | `docker compose up -d` |
| Mettre à jour les images | `docker compose pull && docker compose up -d` |
| Couper l'accès Internet d'urgence | `docker compose stop cloudflared` |

**Sauvegarde minimale**
```bash
tar czf sauvegarde-$(date +%F).tgz /srv/workspace ~/cloud-stack/.env
docker compose exec db mariadb-dump -u root -p"$DB_PASSWORD" nextcloud > nextcloud.sql
```

---

## 6. Partager la pile avec quelqu'un

À donner : `docker-compose.yml`, `hub/`, `terminal/`, `.env.example`, cette fiche.

À **ne jamais** donner :
- ❌ `.env` (mots de passe + token du tunnel = accès à ta machine)
- ❌ `hub/__pycache__/`, `*.bak`
- ❌ le contenu de `/srv/workspace` (tes fichiers, `.agenda.json`, `.liens*.json`)

Ce qui est personnel dans le hub et qu'il adaptera : la section **Hers** (cours, couleurs, logos dans `hers/divers/`, liens).
