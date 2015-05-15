from flask import Flask, render_template, request, url_for, redirect, session
import time
from tinydb import TinyDB, where
from flask.ext.socketio import SocketIO, emit, join_room, leave_room, \
    close_room, disconnect
from threading import Thread
from gevent import monkey

monkey.patch_all()

import json

app = Flask(__name__)
app.debug = True
app.config['SECRET_KEY'] = 'secret!'
db = TinyDB('skorr.json')
socketio = SocketIO(app)
thread = None
overs = 20
team1 = []
team2 = []
striker = ''
nonstriker = ''


@app.route('/teams')
def teams_get():
    return render_template('teams.html')


@app.route('/teams', methods=['POST'])
def teams_post():
    members = request.form.values()
    allplayers = members[1:]
    size = len(allplayers)
    global team1, team2
    team1 = allplayers[:(size / 2)]
    session['team1'] = team1
    team2 = allplayers[(size / 2):]
    session['team2'] = team2
    id = db.insert(request.form)
    print allplayers, team1, team2
    return redirect('/match', code=302)


@app.route('/match', methods=['GET'])
def match_get():
    return render_template('match.html')


@app.route('/match', methods=['POST'])
def match_post():
    id = db.insert(request.form)
    global overs
    overs = request.form['overs']
    session['overs'] = overs
    return redirect('/opening')


@app.route('/opening', methods=['GET'])
def opening_get():
    return render_template('opening.html')


@app.route('/opening', methods=['POST'])
def opening_post():
    id = db.insert(request.form)
    return redirect('/pitch')


@app.route('/pitch', methods=['GET'])
def pitch_get():
    return render_template('pitch.html', arr=json.dumps(session['team1']), arr2=json.dumps(session['team2']))


@app.route('/pitch', methods=['POST'])
def pitch_post():
    global striker, nonstriker
    print(request.form)
    init_player_one()
    return redirect('/over')


@app.route('/over', methods=['GET'])
def over_get():
    return render_template('over.html')


@app.route('/over', methods=['POST'])
def over_post():
    id = db.insert(request.form)
    return render_template('confirm.html', message=id)


@app.route('/commentary', methods=['GET'])
def comm_get():
    return render_template('commentary.html')


@app.route('/scorecard', methods=['GET'])
def sc_get():
    return render_template('scorecard.html')


def background_thread():
    """Example of how to send server generated events to clients."""
    count = 0
    while True:
        time.sleep(10)
        count += 1


@app.route('/')
def index():
    global thread
    session['total'] = 0

    if thread is None:
        thread = Thread(target=background_thread)
        thread.start()
    return render_template('index.html')


@socketio.on('my event', namespace='/test')
def test_message(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    try:
        run = int(message['data'])
        session['total'] = session.get('total', 0) + run
        if run == 0:
            session['dots'] = session.get('dots', 0) + 1
        elif run == 1:
            session['ones'] = session.get('ones', 0) + 1
        elif run == 2:
            session['twos'] = session.get('twos', 0) + 1
        elif run == 3:
            session['threes'] = session.get('threes', 0) + 1
        elif run == 4:
            session['fours'] = session.get('fours', 0) + 1
        elif run == 6:
            session['sixes'] = session.get('sixes', 0) + 1

    except:
        pass

    emit('my response',
         {'data': message['data'], 'count': session['receive_count'], 'total': session['total'],
          'dots': session['dots'],
          'ones': session['ones'],
          'twos': session['twos'], 'threes': session['threes'], 'fours': session['fours'], 'sixes': session['sixes']},
         broadcast=True)


@socketio.on('my broadcast event', namespace='/test')
def test_broadcast_message(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my response',
         {'data': message['data'], 'count': session['receive_count']},
         broadcast=True)


def init_player_one():
    session['dots1'] = 0
    session['ones1'] = 0
    session['twos1'] = 0
    session['threes1'] = 0
    session['fours1'] = 0
    session['sixes1'] = 0


def init_player_two():
    session['dots2'] = 0
    session['ones2'] = 0
    session['twos2'] = 0
    session['threes2'] = 0
    session['fours2'] = 0
    session['sixes2'] = 0


def update_player_one(run):
    if run == 0:
        session['dots1'] = session.get('dots1', 0) + 1
    elif run == 1:
        session['ones1'] = session.get('ones1', 0) + 1
    elif run == 2:
        session['twos1'] = session.get('twos1', 0) + 1
    elif run == 3:
        session['threes1'] = session.get('threes1', 0) + 1
    elif run == 4:
        session['fours1'] = session.get('fours1', 0) + 1
    elif run == 6:
        session['sixes1'] = session.get('sixes1', 0) + 1


def update_player_two(run):
    if run == 0:
        session['dots2'] = session.get('dots2', 0) + 1
    elif run == 1:
        session['ones2'] = session.get('ones2', 0) + 1
    elif run == 2:
        session['twos2'] = session.get('twos2', 0) + 1
    elif run == 3:
        session['threes2'] = session.get('threes2', 0) + 1
    elif run == 4:
        session['fours2'] = session.get('fours2', 0) + 1
    elif run == 6:
        session['sixes2'] = session.get('sixes2', 0) + 1


if __name__ == '__main__':
    socketio.run(app)
