from flask import Flask, render_template

app = Flask(__name__)


@app.route('/', methods=['GET'])
def index_get():
    return render_template('addgroupone.html')

# @app.route('/', methods=['POST'])
# def index_post():



if __name__ == '__main__':
    app.run()
