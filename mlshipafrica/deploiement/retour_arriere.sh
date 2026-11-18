#!/usr/bin/env bash
# Retour à la version d'avant la mise à jour : code ET base tels qu'ils étaient (les saisies faites depuis sont perdues).
# Usage (racine du dépôt) : SERVICE=gunicorn-mlcod bash retour_arriere.sh sauvegardes/AAAAMMJJ-HHMM
set -euo pipefail
SAUV="${1:?Donner le dossier de sauvegarde créé par mise_a_jour.sh}"
PYTHON="${PYTHON:-python3}"
SERVICE="${SERVICE:-}"
RACINE="$(pwd)"
DJANGO="$RACINE/mlshipafrica"
[ -f "$SAUV/base.sql.gz" ] && [ -f "$SAUV/commit_avant.txt" ] || { echo "Sauvegarde incomplète dans $SAUV"; exit 1; }
SAUV="$(cd "$SAUV" && pwd)"
read -r -p "Remettre la base et le code d'avant la mise à jour ? Les saisies faites depuis seront perdues. Taper OUI : " ok
[ "$ok" = "OUI" ] || exit 1
git checkout "$(cat "$SAUV/commit_avant.txt")"
cd "$DJANGO"
"$PYTHON" - > /tmp/.db_mlcod <<'PY'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mlshipafrica.settings')
django.setup()
from django.conf import settings
d = settings.DATABASES['default']
print(d['NAME']); print(d['USER']); print(d['PASSWORD']); print(d['HOST'] or 'localhost'); print(d['PORT'] or '3306')
PY
{ read -r DB_NAME; read -r DB_USER; read -r DB_PASS; read -r DB_HOST; read -r DB_PORT; } < /tmp/.db_mlcod; rm -f /tmp/.db_mlcod
gunzip -c "$SAUV/base.sql.gz" | MYSQL_PWD="$DB_PASS" mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$DB_NAME"
"$PYTHON" manage.py collectstatic --noinput -v0
"$PYTHON" manage.py crontab remove || true
"$PYTHON" manage.py crontab add
[ -n "$SERVICE" ] && sudo systemctl restart "$SERVICE" || echo "Redémarrer l'application à la main."
echo "Retour arrière terminé."
