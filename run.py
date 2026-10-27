"""Start the Flask app on the loopback interface only."""
import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("LIFE_PORT", "5050")), debug=False)
