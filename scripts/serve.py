import os

import uvicorn

#start the fastapi server using uvicorn.
#log_config=None means we let loguru handle logging instead of uvicorn's default logger.
if __name__ == "__main__":
    #set UVICORN_RELOAD=1 (docker-compose sets it for the dev app service) to hot-reload on
    #code changes. left unset in production so the server doesn't watch the filesystem.
    #reload watches the working dir (/app in the container, which only holds the mounted
    #app/, scripts/ and seed/), and re-runs startup warmup (~9s) on each reload.
    reload = os.getenv("UVICORN_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=reload,
        workers=1,
        log_config=None,
    )
