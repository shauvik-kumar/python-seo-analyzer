from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "GSC backend alive"

if __name__ == "__main__":
    app.run()
