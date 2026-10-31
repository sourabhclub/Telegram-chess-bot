import os
import secrets
import threading

import chess
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    manage_session=False,
    ping_interval=25,
    ping_timeout=60,
    async_mode="threading",
)

# In-memory state survives a browser/socket disconnect, but not a server restart.
state_lock = threading.RLock()
waiting_player = None                 # stable player token, not Socket.IO SID
games = {}                            # game_id -> board and player tokens
player_sessions = {}                  # stable player token -> current SID
sid_to_player = {}                    # current SID -> stable player token


def game_for_player(token):
    for game_id, game in games.items():
        if token in (game["white_token"], game["black_token"]):
            return game_id, game
    return None, None


def player_color(game, token):
    if token == game["white_token"]:
        return "white"
    if token == game["black_token"]:
        return "black"
    return None


def send_game_state(game_id, game):
    board = game["board"]
    payload = {
        "game_id": game_id,
        "fen": board.fen(),
        "turn": "white" if board.turn else "black",
        "game_over": board.is_game_over(),
        "result": board.result() if board.is_game_over() else None,
    }
    socketio.emit("game_state", payload, to=game_id)


@app.get("/")
def home():
    return jsonify({"name": "Chess Arena", "status": "online", "message": "Multiplayer chess server is running"})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@socketio.on("register_player")
def register_player(data):
    token = (data or {}).get("player_token", "")
    if not isinstance(token, str) or not token or len(token) > 200:
        emit("error_message", {"message": "Player session is invalid. Refresh the page."})
        return

    sid = request.sid
    with state_lock:
        old_sid = player_sessions.get(token)
        if old_sid and old_sid != sid:
            sid_to_player.pop(old_sid, None)
        player_sessions[token] = sid
        sid_to_player[sid] = token
        game_id, game = game_for_player(token)

        emit("session_ready", {"player_token": token})
        if game_id and game:
            join_room(game_id, sid=sid)
            emit("resume_game", {
                "game_id": game_id,
                "color": player_color(game, token),
                "fen": game["board"].fen(),
                "turn": "white" if game["board"].turn else "black",
                "game_over": game["board"].is_game_over(),
                "result": game["board"].result() if game["board"].is_game_over() else None,
            })
        elif waiting_player == token:
            emit("waiting", {"message": "Waiting for an opponent"})


@socketio.on("find_match")
def find_match():
    global waiting_player
    sid = request.sid
    with state_lock:
        token = sid_to_player.get(sid)
        if not token:
            emit("error_message", {"message": "Session is still initializing. Please tap Find Opponent again."})
            return

        existing_id, existing_game = game_for_player(token)
        if existing_id:
            emit("resume_game", {
                "game_id": existing_id,
                "color": player_color(existing_game, token),
                "fen": existing_game["board"].fen(),
                "turn": "white" if existing_game["board"].turn else "black",
                "game_over": existing_game["board"].is_game_over(),
                "result": existing_game["board"].result() if existing_game["board"].is_game_over() else None,
            })
            return

        if waiting_player == token:
            emit("waiting", {"message": "Waiting for an opponent"})
            return

        if waiting_player:
            opponent_token = waiting_player
            opponent_sid = player_sessions.get(opponent_token)
            # Do not pair against a disconnected waiting browser.
            if opponent_sid and opponent_sid != sid:
                waiting_player = None
                game_id = secrets.token_urlsafe(8)
                board = chess.Board()
                games[game_id] = {
                    "board": board,
                    "white_token": opponent_token,
                    "black_token": token,
                }
                join_room(game_id, sid=opponent_sid)
                join_room(game_id, sid=sid)
                emit("match_found", {"game_id": game_id, "color": "white", "fen": board.fen()}, to=opponent_sid)
                emit("match_found", {"game_id": game_id, "color": "black", "fen": board.fen()}, to=sid)
                return
            waiting_player = None

        waiting_player = token
        emit("waiting", {"message": "Waiting for an opponent"})


@socketio.on("join_game")
def join_game(data):
    sid = request.sid
    game_id = (data or {}).get("game_id", "")
    with state_lock:
        token = sid_to_player.get(sid)
        game = games.get(game_id)
        if not token or not game or token not in (game["white_token"], game["black_token"]):
            emit("error_message", {"message": "Game not found for this session. Try Reconnect."})
            return
        join_room(game_id)
        board = game["board"]
        emit("game_state", {
            "game_id": game_id,
            "fen": board.fen(),
            "turn": "white" if board.turn else "black",
            "game_over": board.is_game_over(),
            "result": board.result() if board.is_game_over() else None,
        })


@socketio.on("make_move")
def make_move(data):
    sid = request.sid
    data = data or {}
    game_id = data.get("game_id", "")
    move_text = data.get("move", "")

    with state_lock:
        token = sid_to_player.get(sid)
        game = games.get(game_id)
        if not game:
            emit("error_message", {"message": "Game not found. Reconnect to restore your game."})
            return
        if not token or token not in (game["white_token"], game["black_token"]):
            emit("error_message", {"message": "You are not in this game. Reconnect to restore your session."})
            return

        color = chess.WHITE if token == game["white_token"] else chess.BLACK
        board = game["board"]
        if board.turn != color:
            emit("error_message", {"message": "Not your turn"})
            return

        try:
            move = chess.Move.from_uci(move_text)
        except (ValueError, TypeError):
            emit("error_message", {"message": "Invalid move format"})
            return

        if move not in board.legal_moves:
            emit("error_message", {"message": "Illegal chess move"})
            return

        board.push(move)
        send_game_state(game_id, game)


@socketio.on("disconnect")
def handle_disconnect():
    global waiting_player
    sid = request.sid
    with state_lock:
        token = sid_to_player.pop(sid, None)
        if token and player_sessions.get(token) == sid:
            player_sessions.pop(token, None)
            if waiting_player == token:
                waiting_player = None
        # Deliberately retain games/board positions so the same token can resume.


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
