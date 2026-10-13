from flask import Flask, jsonify, render_template


app = Flask(__name__, template_folder="frontend/templates")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "LanRouser"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
