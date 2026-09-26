#!/usr/bin/env bash
# Deploy de producao do HoraCerta (EC2). Uso, no servidor:
#   cd /home/ubuntu/horacerta && sudo -u ubuntu git pull origin release-beta-2026-07-10 && sudo bash deploy_prod.sh
# Para no primeiro erro (set -e) e nao reinicia o servico se check/migrate falharem.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

sudo -u ubuntu venv/bin/python manage.py check
sudo -u ubuntu venv/bin/python manage.py migrate
sudo -u ubuntu venv/bin/python manage.py collectstatic --noinput
systemctl restart horacerta
sleep 3
systemctl status horacerta --no-pager -l | head -15
git -c safe.directory="$PWD" log --oneline -1
