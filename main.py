from datetime import date
from typing import Literal
from urllib.parse import quote

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, RedirectResponse

load_dotenv()

import functions

class OrderInfo(BaseModel):
    user_name: str = Field(max_length=5)
    start_date: date
    end_date: date
    order_type: Literal["中餐", "晚餐"]
    form_type: Literal["堂食", "盒饭"]
    remark: str = Field(default='', max_length=500)
    operator: str = Field(max_length=43)

class CheckInfo(BaseModel):
    user_name: str = Field(max_length=5)

class DeleteInfo(BaseModel):
    user_name: str = Field(max_length=5)
    start_date: date
    order_type: Literal["中餐", "晚餐"]
    operator: str = Field(max_length=43)

class UpdateInfo(BaseModel):
    user_name: str = Field(max_length=5)
    start_date: date
    end_date: date
    order_type: Literal["中餐", "晚餐"]
    form_type: Literal["堂食", "盒饭"]
    remark: str = Field(default='', max_length=500)
    operator: str = Field(max_length=43)
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def index():
    return FileResponse(
        "index.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/feishu/login")
def feishu_login(request: Request, force: bool = Query(default=False)):
    cached_operator = None if force else functions._get_cached_feishu_operator(request)
    if cached_operator:
        return RedirectResponse(f"/?operator={quote(cached_operator, safe='')}")

    app_id, _ = functions._feishu_config()
    redirect_uri = quote(functions._feishu_redirect_uri(request), safe="")
    return RedirectResponse(f"{functions.FEISHU_AUTHORIZE_URL}?app_id={app_id}&redirect_uri={redirect_uri}")


@app.get("/feishu/callback", name="feishu_callback")
def feishu_callback(code: str = Query(...), state: str = ""):
    operator = functions._get_feishu_user_name(code)
    response = RedirectResponse(f"/?operator={quote(operator, safe='')}")
    cookie_value, max_age = functions._make_feishu_operator_cookie(operator)
    if max_age > 0:
        response.set_cookie(
            functions.FEISHU_OPERATOR_COOKIE_NAME,
            cookie_value,
            max_age=max_age,
            httponly=True,
            samesite="lax",
            secure=functions._feishu_cookie_secure(),
            path="/",
        )
    return response



@app.post("/submit_order")
def submit_order(order_info: OrderInfo):
    return functions.submit_order(order_info)


@app.get("/check_order")
def check_order(
    user_name: str | None = Query(default=None, max_length=5),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    return functions.check_order(user_name, start_date, end_date)


@app.post("/delete_order")
def delete_order(delete_info: DeleteInfo):
    return functions.delete_order(delete_info)

@app.post("/update_order")
def update_order(update_info: UpdateInfo):
    return functions.update_order(update_info)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
