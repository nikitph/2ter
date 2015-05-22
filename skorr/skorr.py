from flask import Flask, render_template, request, url_for, redirect, session
from tinydb import TinyDB, where
from flask.ext.socketio import SocketIO, emit, join_room, leave_room, \
    close_room, disconnect
from gevent import monkey
from emailer import EmailAssistant
from match import Match
from player import Player

monkey.patch_all()

import json

app = Flask(__name__)
app.debug = True
app.config['SECRET_KEY'] = 'secret!'
db = TinyDB('skorr.json')
socketio = SocketIO(app)
overs = 20
match = None


@app.route('/teams')
def teams_get():
    return render_template('teams.html')


@app.route('/teams', methods=['POST'])
def teams_post():
    session['mtotal'] = 0
    members = request.form.values()
    allplayers = members[1:]
    size = len(allplayers)
    team1 = allplayers[:(size / 2)]
    global match
    session['team1'] = team1
    team2 = allplayers[(size / 2):]
    session['team2'] = team2
    match = Match(team1, team2)
    session['wickets'] = (size / 2) - 1
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
    session['currentovers'] = 0
    session['currentwickets'] = 0
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
    print(request.form)
    session['striker'] = request.form['striker']
    session['playerone'] = request.form['striker']
    session['nonstriker'] = request.form['nonstriker']
    session['playertwo'] = request.form['nonstriker']
    session['validdeliveries'] = 0

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


@app.route('/')
def index():
    session['mtotal'] = 0
    return render_template('index.html')

@app.route('/confirm', methods=['POST'])
def confirm_post():
    email = EmailAssistant()
    email.emailers('alpha@nikitph.com', 'nikitph@gmail.com', request.form['email'], request.form['email'])
    return render_template('confirm.html',
                           message='Thank you for your interest in Skorr. We will let you know as soon as we have an announcement')



def is_valid_delivery():
    return True


@socketio.on('my event', namespace='/test')
def test_message(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    response = {}
    response['endofinnings'] = False
    isNoBall = message['noball']
    isWideBall = message['wide']
    isValid = not message['invalid']
    isBye = message['bye']
    isLegBye = message['legbye']
    isWicket = message['wicket']
    global match
    try:
        run = int(message['data'])
        session['mtotal'] = session.get('mtotal', 0) + run
        striker = match.get_player(session['striker'])
        if isNoBall:
            if message['nbe']:
                update_striker(run-1)
            else:
                striker.update_runs(run-1)
                update_striker(run-1)

        elif isWideBall:
            update_striker(run-1)

        elif isLegBye:
            update_striker(run)

        elif isBye:
            update_striker(run)

        elif isWicket:
            session['currentwickets'] += 1
            if session['currentwickets'] == session['wickets']:
                response['endofinnings'] = True
            if not response['endofinnings']:
                if message['stikerout']:
                    session['striker'] = match.get_next_player(session['currentwickets'] + 2)
                    session['playerone'] = session['striker']

                else:
                    session['nonstriker'] = match.get_next_player(session['currentwickets'] + 2)
                    session['playertwo'] = session['nonstriker']

        else:
            striker.update_runs(run)
            update_striker(run)

        if isValid:
            session['validdeliveries'] += 1

        scorecard_dict = []
        for p in match.get_all_players(1):
            temp = match.get_player(p)
            scorecard_dict.append(temp.return_runs())

        response['scorecard'] = scorecard_dict
        response['playerone'] = session['playerone']
        player_1 = match.get_player(session['playerone'])
        response['playeroneruns'] = player_1.total()
        response['playertwo'] = session['playertwo']
        player_2 = match.get_player(session['playertwo'])
        response['playertworuns'] = player_2.total()
        response['endofover'] = False

        if session['validdeliveries'] == 6:
            response['endofover'] = True
            session['validdeliveries'] = 0
            update_striker(1)
            session['currentovers'] += 1
            if session['currentovers'] == session['overs']:
                response['endofinnings'] = True


    except Exception as e:
        print(str(e))

    response['data'] = message['data']
    response['count'] = session['receive_count']
    response['mtotal'] = session['mtotal']
    emit('my response', response, broadcast=True)


@socketio.on('my broadcast event', namespace='/test')
def test_broadcast_message(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my response',
         {'data': message['data'], 'count': session['receive_count']},
         broadcast=True)


def init_player_one(name):
    player_one = Player(name)
    return player_one


def init_player_two(name):
    player_two = Player(name)
    return player_two


def update_striker(run):
    if run % 2 == 0:
        pass
    elif run % 2 == 1:
        temp = session['striker']
        session['striker'] = session['nonstriker']
        session['nonstriker'] = temp


if __name__ == '__main__':
    socketio.run(app)
