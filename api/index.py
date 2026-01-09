from app import create_app

app = create_app()

# Vercel serverless handler
def handler(request):
    return app(request.environ, lambda *args: None)

# For local testing
if __name__ == "__main__":
    app.run()
