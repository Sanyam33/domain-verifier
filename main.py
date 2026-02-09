from fastapi import FastAPI
import router

app = FastAPI()


app.include_router(router.domain_router)

@app.get("/")
def hello():
    return {"Hello": "World"}