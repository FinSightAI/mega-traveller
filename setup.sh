#!/bin/bash
# התקנה מהירה של MegaTraveller

echo "🌍 מתקין MegaTraveller..."

# Create virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install deps
pip install -q -r requirements.txt

# Setup .env if missing
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  ערוך את קובץ .env והכנס את מפתח ה-API שלך:"
    echo "   ANTHROPIC_API_KEY=sk-ant-..."
    echo ""
fi

echo "✅ הותקן בהצלחה!"
echo ""
echo "הפעלה:"
echo "  source .venv/bin/activate"
echo "  python main.py"
