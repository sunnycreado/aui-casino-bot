from flask import Flask, request, jsonify, send_from_directory
import os
import signal
import json
from dotenv import load_dotenv, set_key
import sys
import subprocess
import threading
import time

app = Flask(__name__)
CONFIG_FILE = 'config.json'
DOTENV_FILE = '.env'

bot_process = None

def get_token():
    load_dotenv(DOTENV_FILE)
    return os.getenv('DISCORD_TOKEN', '')

def set_token(token):
    set_key(DOTENV_FILE, 'DISCORD_TOKEN', token)

def start_bot():
    global bot_process
    if bot_process and bot_process.poll() is None:
        return  # Already running
    bot_process = subprocess.Popen([sys.executable, 'bot_runner.py'])

def stop_bot():
    global bot_process
    if bot_process and bot_process.poll() is None:
        bot_process.terminate()
        try:
            bot_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            bot_process.kill()
    bot_process = None

@app.route('/')
def serve_frontend():
    return send_from_directory('.', 'frontend_ui.html')

@app.route('/api/token', methods=['GET'])
def api_get_token():
    token = get_token()
    return jsonify({'token': token})

@app.route('/api/token', methods=['POST'])
def api_set_token():
    data = request.get_json()
    token = data.get('token', '')
    set_token(token)
    return jsonify({'success': True, 'token': token})

@app.route('/api/restart', methods=['POST'])
def api_restart():
    stop_bot()
    time.sleep(1)
    start_bot()
    return jsonify({'success': True})

if __name__ == '__main__':
    threading.Thread(target=start_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False) 