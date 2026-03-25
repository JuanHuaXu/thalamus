# Thalamus Service Manager - v2.3 (Restoration Edition)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
APP_NAME="thalamus"
PORT=8080
LOG_FILE="$BASE_DIR/logs/thalamus.log"
PID_FILE="$BASE_DIR/logs/thalamus.pid"
VENV_PATH="$BASE_DIR/.venv"

mkdir -p "$BASE_DIR/logs"

start() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "⚠️ $APP_NAME is already running (PID: $(cat $PID_FILE))."
        return
    fi

    echo "🚀 Starting $APP_NAME on port $PORT..."
    if [ ! -d "$VENV_PATH" ]; then
        echo "❌ Error: Virtual environment not found at $VENV_PATH. Run scripts/install.sh first."
        exit 1
    fi
    source "$VENV_PATH/bin/activate"
    export PYTHONPATH="$BASE_DIR/src"
    cd "$BASE_DIR"
    nohup python3 -m uvicorn thalamus.main:app --host 127.0.0.1 --port $PORT > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    
    sleep 2
    if kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "✅ $APP_NAME started (PID: $(cat $PID_FILE)). Logs: $LOG_FILE"
    else
        echo "❌ Failed to start $APP_NAME. Check $LOG_FILE for details."
        rm -f "$PID_FILE"
    fi
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "⚠️ $APP_NAME is not running."
        # Fallout check for rogue processes
        rogue_pids=$(lsof -t -i :$PORT)
        if [ ! -z "$rogue_pids" ]; then
            echo "🕵️ Found rogue processes on port $PORT. Killing..."
            kill -9 $rogue_pids
        fi
        return
    fi
    
    pid=$(cat "$PID_FILE")
    echo "🛑 Stopping $APP_NAME (PID: $pid)..."
    kill $pid
    rm -f "$PID_FILE"
    
    # Secondary check
    sleep 1
    lsof -i :$PORT | grep LISTEN | awk '{print $2}' | xargs kill 2>/dev/null
    echo "✅ $APP_NAME stopped."
}

status() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "🟢 $APP_NAME is running (PID: $(cat $PID_FILE))."
        echo "🔗 API Docs: http://127.0.0.1:$PORT/docs"
    else
        echo "🔴 $APP_NAME is not running."
    fi
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
esac
