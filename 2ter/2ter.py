from flask import Flask, render_template, request
from emailer import EmailAssistant

app = Flask(__name__)


@app.route('/')
def hello_world():
    return render_template('base.html')

@app.route('/contactus', methods=['POST'])
def contact_post():
    email = EmailAssistant()
    email.emailers('alpha@nikitph.com', 'nikitph@gmail.com', request.form['email'], request.form['email'])
    return render_template('confirm.html')


if __name__ == '__main__':
    app.run()
