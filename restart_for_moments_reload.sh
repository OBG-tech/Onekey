#!/bin/bash
# Restart the integrated system to reload updated moments.json

echo "🔄 Restarting the integrated system to load updated moments..."
echo ""

# Find the PID of the running system
PID=$(ps aux | grep -E "python.*start_multicam_system.py.*8082" | grep -v grep | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "❌ No running system found on port 8082"
    echo "You can start it manually with:"
    echo "  python3 start_multicam_system.py --cameras 0,2,4,6 --fps 30 --resolution 1280x720 --port 8082 --record"
    exit 1
fi

echo "📍 Found running system (PID: $PID)"
echo "⏹️  Stopping the system..."

# Gracefully stop the system
kill -SIGTERM $PID

# Wait for it to stop (max 10 seconds)
for i in {1..10}; do
    if ! ps -p $PID > /dev/null 2>&1; then
        echo "✅ System stopped"
        break
    fi
    echo "   Waiting... ($i/10)"
    sleep 1
done

# Force kill if still running
if ps -p $PID > /dev/null 2>&1; then
    echo "⚠️  Force stopping..."
    kill -9 $PID
    sleep 1
fi

echo ""
echo "✅ System stopped successfully"
echo ""
echo "To restart with all 159 moments loaded, run:"
echo "  python3 start_multicam_system.py --cameras 0,2,4,6 --fps 30 --resolution 1280x720 --port 8082 --record"
echo ""
echo "Or use one of the existing startup scripts:"
echo "  ./start_multi_camera.sh"
echo "  ./start_macos.sh"
