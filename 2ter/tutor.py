from flask import Flask, render_template, request
from emailer import EmailAssistant

applic = Flask(__name__)


@applic.route('/')
def hello_world():
    return render_template('base.html')


@applic.route('/confirm', methods=['POST'])
def confirm_post():
    email = EmailAssistant()
    email.emailers('alpha@nikitph.com', 'nikitph@gmail.com', request.form['email'], request.form['email'])
    return render_template('confirm.html',
                           message='Thank you for your interest in 2^tr. We will let you know as soon as we have an announcement')


@applic.route('/contactus', methods=['GET'])
def contact_get():
    return render_template('contact.html')


@applic.route('/contactus', methods=['POST'])
def contact_post():
    email = EmailAssistant()
    email.emailers('alpha@nikitph.com', 'nikitph@gmail.com',
                   'Message from ' + request.form['name'] + ' :' + request.form['email'], request.form['message'])
    return render_template('confirm.html', message='Thank you for your interest in 2^tr')

@applic.route('/about', methods=['GET'])
def about_get():
    return render_template('about.html')


if __name__ == '__main__':
    applic.run()
