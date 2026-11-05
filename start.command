#!/bin/bash
# bash, macOS: запуск Menu Simulator одним файлом (двойной клик или ./start.command)
cd "$(dirname "$0")" || exit 1

if [ ! -d venv ]; then
  echo "создаю venv..."; python3 -m venv venv || exit 1
fi
source venv/bin/activate
python -c "import streamlit, plotly, pandas, openpyxl, requests" 2>/dev/null || {
  echo "ставлю зависимости..."; pip install -q -r requirements.txt || exit 1; }

# ключи по желанию: положи их в файл .env рядом (ANTHROPIC_API_KEY=...), он не попадает в git
[ -f .env ] && set -a && . ./.env && set +a
[ -z "$ANTHROPIC_API_KEY" ] && echo "ANTHROPIC_API_KEY не задан: агент и персоны работают на правилах (без LLM)"

# MiroFish (необязательно): поднимется, если контейнер уже создан
if command -v docker >/dev/null 2>&1 && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx mirofish; then
  docker start mirofish >/dev/null 2>&1 && echo "MiroFish: контейнер запущен"
else
  echo "MiroFish не найден (вкладка-эксперимент будет неактивна, остальное работает)"
fi

python -m unittest discover -s tests >/tmp/menu_tests.log 2>&1 && echo "тесты: ok" || echo "тесты: есть падения, см. /tmp/menu_tests.log"
exec streamlit run app.py