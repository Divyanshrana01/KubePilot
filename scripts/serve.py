import uvicorn

#start the fastapi server using uvicorn.
#log_config=None means we let loguru handle logging instead of uvicorn's default logger.
if __name__=='__main__':
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        workers=1,
        log_config=None
    )