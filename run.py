from app import create_app
import os

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("LIFE_PORT", "5050")), debug=False)
