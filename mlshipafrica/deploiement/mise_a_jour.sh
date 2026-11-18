#!/usr/bin/env bash
# Mise à jour ML COD Intérieur en production, données conservées.
# Usage (depuis la racine du dépôt, celle qui contient le dossier mlshipafrica/) :
#   SERVICE=gunicorn-mlcod bash mise_a_jour.sh /chemin/vers/ml-cod-recette-18-11.bundle
# Variables : SERVICE (service systemd à redémarrer, facultatif), PYTHON (python du virtualenv, défaut : python3).
set -euo pipefail

BUNDLE="${1:?Donner le chemin du fichier ml-cod-recette-18-11.bundle}"
PYTHON="${PYTHON:-python3}"
SERVICE="${SERVICE:-}"
RACINE="$(pwd)"
DJANGO="$RACINE/mlshipafrica"
DATE="$(date +%Y%m%d-%H%M)"
SAUV="$RACINE/sauvegardes/$DATE"

[ -f "$DJANGO/manage.py" ] || { echo "Lancer depuis la racine du dépôt (dossier qui contient mlshipafrica/manage.py)"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "Modifications locales non enregistrées : git status. Arrêt."; exit 1; }
git merge-base --is-ancestor 1d774fd HEAD || { echo "Le commit 1d774fd n'est pas dans la version en ligne. Arrêt : prévenir Romuald."; exit 1; }
grep -qi '^RECETTE *= *true' "$DJANGO/.env" 2>/dev/null && { echo "RECETTE=True dans le .env de production : à retirer. Arrêt."; exit 1; }

echo "== 1/6 Sauvegarde de la base et du code dans $SAUV"
mkdir -p "$SAUV"
git rev-parse HEAD > "$SAUV/commit_avant.txt"
cd "$DJANGO"
"$PYTHON" - > "$SAUV/.db" <<'PY'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mlshipafrica.settings')
django.setup()
from django.conf import settings
d = settings.DATABASES['default']
print(d['NAME']); print(d['USER']); print(d['PASSWORD']); print(d['HOST'] or 'localhost'); print(d['PORT'] or '3306')
PY
{ read -r DB_NAME; read -r DB_USER; read -r DB_PASS; read -r DB_HOST; read -r DB_PORT; } < "$SAUV/.db"
rm -f "$SAUV/.db"
MYSQL_PWD="$DB_PASS" mysqldump --single-transaction --routines --no-tablespaces -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$DB_NAME" \
  | gzip > "$SAUV/base.sql.gz"
[ -s "$SAUV/base.sql.gz" ] || { echo "Sauvegarde vide : arrêt, rien n'a été modifié."; exit 1; }
echo "   base sauvegardée : $(du -h "$SAUV/base.sql.gz" | cut -f1)"
cd "$RACINE"

echo "== 2/6 Nouveau code"
git fetch "$BUNDLE" "ml-cod-interieur/recette-18-11:mise-a-jour-18-11"
git checkout mise-a-jour-18-11

echo "== 3/6 Réglages (.env)"
grep -q '^STOCKAGE_MENSUEL_DEPUIS' "$DJANGO/.env" || echo 'STOCKAGE_MENSUEL_DEPUIS=2026-12' >> "$DJANGO/.env"

cd "$DJANGO"
echo "== 4/6 Vérification puis mise à jour de la base (ajouts seulement : aucune donnée supprimée)"
"$PYTHON" manage.py check
"$PYTHON" manage.py migrate --plan
"$PYTHON" manage.py migrate --noinput
"$PYTHON" manage.py collectstatic --noinput -v0

echo "== 5/6 Tâches planifiées"
"$PYTHON" manage.py crontab remove || true
"$PYTHON" manage.py crontab add

echo "== 6/6 Redémarrage"
if [ -n "$SERVICE" ]; then sudo systemctl restart "$SERVICE" && systemctl --no-pager --lines=0 status "$SERVICE" || true
else echo "   SERVICE non donné : redémarrer l'application à la main (gunicorn / uwsgi / Passenger)."; fi

cd "$RACINE"
echo
echo "Mise à jour terminée. Sauvegarde : $SAUV  (retour arrière : bash retour_arriere.sh $SAUV)"
