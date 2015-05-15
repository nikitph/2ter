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
total = 0
dots = 0
ones = 0
twos = 0
threes = 0
fours = 0
sixes = 0


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
    team2 = allplayers[(size / 2):]
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
    global team1, team2
    return render_template('pitch.html', arr=json.dumps(team1), arr2=json.dumps(team2))


@app.route('/pitch', methods=['POST'])
def pitch_post():
    global striker, nonstriker
    print(request.form)
    return redirect('/over')


@app.route('/over', methods=['GET'])
def over_get():
    global team1, team2
    return render_template('over.html', arr=json.dumps(team1), arr2=json.dumps(team2))


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
    if thread is None:
        thread = Thread(target=background_thread)
        thread.start()
    return render_template('index.html')


@socketio.on('my event', namespace='/test')
def test_message(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    global total
    try:
        run = int(message['data'])
        total += run
        if (run == 0):
            pass
        elif (run == 1):
            session['ones'] = session.get('ones', 0) + 1
        elif (run == 2):
            session['twos'] = session.get('twos', 0) + 1
        elif (run == 3):
            session['threes'] = session.get('threes', 0) + 1
        elif (run == 4):
            session['fours'] = session.get('fours', 0) + 1
        elif (run == 6):
            session['sixes'] = session.get('sixes', 0) + 1

    except:
        pass

        emit('my response',
             {'data': message['data'], 'count': session['receive_count'], 'total': total, 'dots': 2, 'ones':  session['ones'],
              'twos': session['twos'], 'threes': session['threes'], 'fours': session['fours'], 'sixes': session['sixes']}, broadcast=True)


@socketio.on('my broadcast event', namespace='/test')
def test_broadcast_message(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my response',
         {'data': message['data'], 'count': session['receive_count']},
         broadcast=True)


if __name__ == '__main__':
    socketio.run(app)
