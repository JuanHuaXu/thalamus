#!/bin/bash
# Thalamus Installation Script - v2.3 (Restoration Edition)

set -e

echo "🚀 Installing Thalamus (Race Car Edition)..."

# 1. Check for Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed. Please install it first."
    exit 1
fi

# 2. Create Virtual Environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# 3. Install Dependencies
echo "📥 Installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Bootstrap Config
if [ ! -f "config.json" ]; then
    echo "⚙️ Creating default config.json from example..."
    if [ -f "config.json.example" ]; then
        cp config.json.example config.json
    else
        echo '{"host": "127.0.0.1", "port": 8080, "llm_model_name": "llama3:8b"}' > config.json
    fi
fi

# 5. Create Log Directory
mkdir -p logs

echo "✅ Installation complete! Use 'scripts/service.sh start' to run Thalamus."
