import os
import secrets
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, join_room, emit
import chess

app = Flask(name)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))
socketio = SocketIO(app, cors_allowed_origins="*")

waiting_player = None
games = {}

@app.get("/")
def home():
return jsonify({
"name": "Chess Arena",
"status": "online",
"message": "Multiplayer chess server is running"
})

@app.get("/health")
def health():
return jsonify({"status": "ok"})

@socketio.on("find_match")
def find_match():
global waiting_player

sid = request.sid

if waiting_player and waiting_player != sid:
    white_sid = waiting_player
    black_sid = sid
    waiting_player = None

    game_id = secrets.token_urlsafe(8)
    board = chess.Board()

    games[game_id] = {
        "board": board,
        "white": white_sid,
        "black": black_sid
    }

    join_room(game_id)

    emit(
        "match_found",
        {"game_id": game_id, "color": "white", "fen": board.fen()},
        to=white_sid
    )
    emit(
        "match_found",
        {"game_id": game_id, "color": "black", "fen": board.fen()},
        to=black_sid
    )
else:
    waiting_player = sid
    emit("waiting", {"message": "Waiting for an opponent"})

@socketio.on("join_game")
def join_game(data):
game_id = data.get("game_id", "")
game = games.get(game_id)

if not game or request.sid not in (game["white"], game["black"]):
    emit("error_message", {"message": "Game not found"})
    return

join_room(game_id)

emit("game_state", {
    "fen": game["board"].fen(),
    "turn": "white" if game["board"].turn else "black"
})

@socketio.on("make_move")
def make_move(data):
game_id = data.get("game_id", "")
game = games.get(game_id)

if not game:
    emit("error_message", {"message": "Game not found"})
    return

sid = request.sid

if sid == game["white"]:
    player_color = chess.WHITE
elif sid == game["black"]:
    player_color = chess.BLACK
else:
    emit("error_message", {"message": "You are not in this game"})
    return

board = game["board"]

if board.turn != player_color:
    emit("error_message", {"message": "Not your turn"})
    return

try:
    move = chess.Move.from_uci(data["move"])
except (ValueError, KeyError, TypeError):
    emit("error_message", {"message": "Invalid move format"})
    return

if move not in board.legal_moves:
    emit("error_message", {"message": "Illegal chess move"})
    return

board.push(move)

result = {
    "fen": board.fen(),
    "move": move.uci(),
    "turn": "white" if board.turn else "black",
    "game_over": board.is_game_over(),
    "result": board.result() if board.is_game_over() else None
}

emit("game_state", result, to=game_id)

@socketio.on("disconnect")
def disconnect():
global waiting_player

if waiting_player == request.sid:
    waiting_player = None

if name == "main":
port = int(os.environ.get("PORT", "5000"))
socketio.run(app, host="0.0.0.0", port=port)
