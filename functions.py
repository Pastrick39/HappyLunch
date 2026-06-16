import base64
import hashlib
import hmac
import os
import time as time_module
from datetime import date, datetime, time, timedelta
import requests
from fastapi import HTTPException, Request

import DBtools

FEISHU_AUTHORIZE_URL = os.getenv(
    "FEISHU_AUTHORIZE_URL",
    "https://open.feishu.cn/open-apis/authen/v1/index",
)
FEISHU_APP_ID = "cli_aa8973ab35f85cd9"
FEISHU_APP_SECRET = "9W7TqWR4zxgXkuXI1HNabe23xC4eatC3"
FEISHU_REDIRECT_URI = "http://223.78.73.100:8010/feishu/callback"
FEISHU_APP_ACCESS_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal"
FEISHU_USER_ACCESS_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v1/access_token"
FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
FEISHU_OPERATOR_COOKIE_NAME = os.getenv("FEISHU_OPERATOR_COOKIE_NAME", "happy_lunch_operator")
FEISHU_OPERATOR_CACHE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
FEISHU_APP_ACCESS_TOKEN_CACHE_SECONDS = 100 * 60
HR_DEPARTMENT_KEYWORDS = ("人力", "人力资源", "人事", "人资")


_FEISHU_APP_ACCESS_TOKEN_CACHE = {"token": "", "expires_at": 0.0}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _feishu_operator_cache_max_age() -> int:
    return max(0, _int_env("FEISHU_OPERATOR_CACHE_MAX_AGE_SECONDS", FEISHU_OPERATOR_CACHE_MAX_AGE_SECONDS))


def _feishu_cookie_secure() -> bool:
    return os.getenv("FEISHU_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}


def _feishu_cookie_secret(app_id: str, app_secret: str) -> str:
    return os.getenv("FEISHU_COOKIE_SECRET", "").strip() or app_secret or app_id


def _encode_cookie_text(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cookie_text(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii")).decode("utf-8")


def _sign_feishu_operator(operator: str, issued_at: int, secret: str) -> str:
    message = f"{operator}|{issued_at}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _make_feishu_operator_cookie(operator: str) -> tuple[str, int]:
    app_id, app_secret = _feishu_config()
    issued_at = int(time_module.time())
    signature = _sign_feishu_operator(operator, issued_at, _feishu_cookie_secret(app_id, app_secret))
    return f"{_encode_cookie_text(operator)}.{issued_at}.{signature}", _feishu_operator_cache_max_age()


def _get_cached_feishu_operator(request: Request) -> str | None:
    cookie_value = request.cookies.get(FEISHU_OPERATOR_COOKIE_NAME, "")
    parts = cookie_value.split(".")
    if len(parts) != 3:
        return None

    encoded_operator, issued_at_text, signature = parts
    try:
        issued_at = int(issued_at_text)
        operator = _decode_cookie_text(encoded_operator).strip()
    except (TypeError, ValueError, UnicodeDecodeError):
        return None

    max_age = _feishu_operator_cache_max_age()
    if not operator or max_age <= 0 or time_module.time() - issued_at > max_age:
        return None

    app_id, app_secret = _feishu_config()
    expected_signature = _sign_feishu_operator(operator, issued_at, _feishu_cookie_secret(app_id, app_secret))
    if not hmac.compare_digest(signature, expected_signature):
        return None
    return operator


def _feishu_config() -> tuple[str, str]:
    app_id = os.getenv("FEISHU_APP_ID", FEISHU_APP_ID).strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", FEISHU_APP_SECRET).strip()
    if not app_id or not app_secret:
        raise HTTPException(
            status_code=500,
            detail="请先配置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET。",
        )
    return app_id, app_secret


def _feishu_redirect_uri(request: Request) -> str:
    configured = os.getenv("FEISHU_REDIRECT_URI", FEISHU_REDIRECT_URI).strip()
    if configured:
        return configured
    return str(request.url_for("feishu_callback"))


def _extract_feishu_data(response: requests.Response, action: str) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"{action}失败：飞书返回非 JSON 响应。") from exc

    if response.status_code >= 400 or payload.get("code", 0) != 0:
        message = payload.get("msg") or payload.get("message") or response.text
        raise HTTPException(status_code=502, detail=f"{action}失败：{message}")
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _get_feishu_app_access_token(app_id: str, app_secret: str) -> str:
    now = time_module.time()
    cached_token = _FEISHU_APP_ACCESS_TOKEN_CACHE.get("token")
    cached_expires_at = float(_FEISHU_APP_ACCESS_TOKEN_CACHE.get("expires_at") or 0)
    if cached_token and cached_expires_at > now:
        return str(cached_token)

    response = requests.post(
        FEISHU_APP_ACCESS_TOKEN_URL,
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    data = _extract_feishu_data(response, "获取飞书 app_access_token")
    token = data.get("app_access_token")
    if not token:
        raise HTTPException(status_code=502, detail="获取飞书 app_access_token 失败：响应中没有 token。")
    cache_seconds = max(0, _int_env("FEISHU_APP_ACCESS_TOKEN_CACHE_SECONDS", FEISHU_APP_ACCESS_TOKEN_CACHE_SECONDS))
    _FEISHU_APP_ACCESS_TOKEN_CACHE.update({"token": token, "expires_at": now + cache_seconds})
    return token


def _get_feishu_user_name(code: str) -> str:
    app_id, app_secret = _feishu_config()
    app_access_token = _get_feishu_app_access_token(app_id, app_secret)
    token_response = requests.post(
        FEISHU_USER_ACCESS_TOKEN_URL,
        headers={
            "Authorization": f"Bearer {app_access_token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={"grant_type": "authorization_code", "code": code},
        timeout=10,
    )
    token_data = _extract_feishu_data(token_response, "获取飞书 user_access_token")
    user_access_token = token_data.get("access_token") or token_data.get("user_access_token")
    if not user_access_token:
        raise HTTPException(status_code=502, detail="获取飞书 user_access_token 失败：响应中没有 token。")

    user_response = requests.get(
        FEISHU_USER_INFO_URL,
        headers={"Authorization": f"Bearer {user_access_token}"},
        timeout=10,
    )
    user_data = _extract_feishu_data(user_response, "获取飞书登录用户信息")
    user_name = (
        user_data.get("name")
        or user_data.get("cn_name")
        or user_data.get("en_name")
        or user_data.get("nickname")
    )
    if not user_name:
        raise HTTPException(status_code=502, detail="获取飞书登录用户信息失败：响应中没有用户名称。")
    return str(user_name)


def _db_select(sql: str, params=None):
    '''
    确保数据库读取稳定
    :param sql:
    :param params:
    :return:
    '''
    last_exc = None
    for _ in range(3):
        try:
            return DBtools.sf_db(sql, params)
        except Exception as exc:
            last_exc = exc
            time_module.sleep(0.5)
    raise last_exc


def _db_write(sql: str, params=None):
    '''
    确保数据库写入稳定
    :param sql:
    :param params:
    :return:
    '''
    last_exc = None
    for _ in range(3):
        try:
            return DBtools.dui_db(sql, params)
        except Exception as exc:
            last_exc = exc
            time_module.sleep(0.5)
    raise last_exc


def _ensure_user_exists(user_name: str):
    '''
    确保用户存在于ComputerName表中
    :param user_name:
    :return:
    '''
    normalized_name = user_name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="请填写订餐人。")

    try:
        exists_count = _db_select(
            "SELECT COUNT(*) FROM ComputerName WHERE UName = %(user_name)s "
            "AND UName IS NOT NULL "
            "AND UName != ''",
            {"user_name": normalized_name},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"校验订餐人失败：{exc}") from exc

    if int(exists_count or 0) <= 0:
        raise HTTPException(status_code=400, detail=f"{normalized_name} 不在 ComputerName 表中，不允许订饭。")

    return normalized_name


def _is_hr_operator(operator: str) -> bool:
    '''
    判断是否为人力部门
    :param operator:
    :return:
    '''
    normalized_operator = (operator or "").strip()
    if not normalized_operator:
        return False

    try:
        department = _db_select(
            "SELECT TOP 1 BuMen FROM ComputerName WHERE UName = %(operator)s",
            {"operator": normalized_operator},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"校验操作人部门失败：{exc}") from exc

    department_text = str(department or "").strip()
    return any(keyword in department_text for keyword in HR_DEPARTMENT_KEYWORDS)



def _is_proxy_order(order_info) -> bool:
    '''
    判断是给自己订餐还是别人
    :param order_info:
    :return:
    '''
    return order_info.operator.strip() != order_info.user_name.strip()


def _is_proxy_action(operator: str, user_name: str) -> bool:
    return operator.strip() != user_name.strip()



def _get_email_recipient(user_name: str) -> str:
    '''
    如果是代订，查找订餐人的邮箱
    :param user_name:
    :return:
    '''
    try:
        row = _db_select(
            "SELECT * FROM v_YouXiang WHERE UName = %(user_name)s",
            {"user_name": user_name},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"查询{user_name}邮箱失败：{exc}") from exc

    recipient = ""
    if isinstance(row, list) and row and isinstance(row[0], tuple):
        recipient = ";".join(str(v) for v in row[0][1:] if v)
    elif isinstance(row, tuple) and len(row) > 1:
        recipient = ";".join(str(v) for v in row[1:] if v)
    elif isinstance(row, str):
        recipient = row

    if not recipient:
        raise HTTPException(status_code=500, detail=f"未找到{user_name}的邮箱，代订饭通知未发送。")
    return recipient


def _send_proxy_order_email(order_info, inserted_dates: list[date], recipient: str) -> bool:
    '''
    代订发送邮件
    :param order_info:
    :param inserted_dates:
    :param recipient:
    :return:
    '''
    if not inserted_dates:
        return False
    dates_text = "、".join(d.strftime("%Y-%m-%d") for d in inserted_dates)
    title = "代订饭通知"
    body = f"{order_info.user_name} 你好，{order_info.operator}已帮你订了{dates_text}的{order_info.form_type}{order_info.order_type}。"
    applicant = f"FeiShu@{order_info.operator}"
    sql = """
    INSERT INTO FaYouJian
    VALUES (%(applicant)s, %(recipient)s, %(title)s, %(body)s, GETDATE(), '', '')
    """
    _db_write(sql, {
        "applicant": applicant,
        "recipient": recipient,
        "title": title,
        "body": body,
    })
    return True


def _send_proxy_cancel_email(delete_info, recipient: str) -> bool:
    '''
    代取消发送邮件
    :param delete_info:
    :param recipient:
    :return:
    '''
    title = "代取消订饭通知"
    body = f"{delete_info.user_name} 你好，{delete_info.operator}已帮你取消了{delete_info.start_date.strftime('%Y-%m-%d')}的{delete_info.order_type}。"
    applicant = f"FeiShu@{delete_info.operator}"
    sql = """
    INSERT INTO FaYouJian
    VALUES (%(applicant)s, %(recipient)s, %(title)s, %(body)s, GETDATE(), '', '')
    """
    _db_write(sql, {
        "applicant": applicant,
        "recipient": recipient,
        "title": title,
        "body": body,
    })
    return True


def _send_proxy_update_email(update_info, updated_dates: list[date], recipient: str) -> bool:
    '''
    代修改订餐形式发送邮件
    :param update_info:
    :param updated_dates:
    :param recipient:
    :return:
    '''
    if not updated_dates:
        return False
    dates_text = "、".join(d.strftime("%Y-%m-%d") for d in updated_dates)
    title = "代修改订饭通知"
    body = f"{update_info.user_name} 你好，{update_info.operator}已帮你把{dates_text}的{update_info.order_type}修改为{update_info.form_type}。"
    applicant = f"FeiShu@{update_info.operator}"
    sql = """
    INSERT INTO FaYouJian
    VALUES (%(applicant)s, %(recipient)s, %(title)s, %(body)s, GETDATE(), '', '')
    """
    _db_write(sql, {
        "applicant": applicant,
        "recipient": recipient,
        "title": title,
        "body": body,
    })
    return True


def _fraction_day_to_time(value) -> time:
    '''
    将 YouJianTongZhi 中的天数小数转换为 time，例如 0.38889 约等于 09:20。
    :param value:
    :return:
    '''
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time().replace(second=0, microsecond=0)

    try:
        fraction = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"订饭截止时间配置无效：{value}") from exc

    if fraction < 0 or fraction >= 1:
        raise HTTPException(status_code=500, detail=f"订饭截止时间配置超出范围：{value}")

    total_minutes = round(fraction * 24 * 60)
    hour, minute = divmod(total_minutes, 60)
    return time(hour, minute)


def _get_deadline(setting_prefix: str, order_type: str) -> time:
    '''
    从 YouJianTongZhi 读取截止时间。
    :param setting_prefix:
    :param order_type:
    :return:
    '''
    setting_name = f"{setting_prefix}_{order_type}"
    try:
        setting_value = _db_select(
            "SELECT ShouJianRen FROM YouJianTongZhi WHERE ShiXiang = %(setting_name)s",
            {"setting_name": setting_name},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取{setting_name}失败：{exc}") from exc

    if setting_value in ("", None, []):
        raise HTTPException(status_code=500, detail=f"未配置{setting_name}。")

    return _fraction_day_to_time(setting_value)





def _get_order_deadline(order_type: str) -> time:
    return _get_deadline("订饭截止", order_type)


def _get_cancel_deadline(order_type: str) -> time:
    return _get_deadline("订饭截止", order_type)


ORDER_USAGE_LOG_ACTION = "\u8ba2\u996d"
ORDER_USAGE_LOG_CANCEL_ACTION = "\u53d6\u6d88\u8ba2\u996d"
ORDER_USAGE_LOG_DATE_LABEL = "\u65e5\u671f"
ORDER_USAGE_LOG_FORM_LABEL = "\u5f62\u5f0f"
ORDER_USAGE_LOG_REMARK_LABEL = "\u5907\u6ce8"
ORDER_USAGE_LOG_TYPE_LABEL = "\u7c7b\u578b"
ORDER_USAGE_LOG_OPERATOR_LABEL = "\u64cd\u4f5c\u4eba"


def _get_order_usage_user_id(user_name: str) -> str:
    try:
        user_id = _db_select(
            """
            SELECT MIN(CNID)
              FROM ComputerName
             WHERE UName = %(user_name)s
               AND UName IS NOT NULL
               AND UName != ''
            """,
            {"user_name": user_name},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"\u83b7\u53d6\u8ba2\u9910\u4ebaUserID\u5931\u8d25\uff1a{exc}") from exc

    if user_id in ("", None, []):
        raise HTTPException(status_code=500, detail=f"\u672a\u627e\u5230{user_name}\u7684UserID\u3002")
    return f"{int(user_id):04d}"


def _order_usage_log_params(order_info, order_date: date, cnun: str, usage_user_id: str) -> dict:
    remark = (order_info.remark or "").strip()
    menu = (
        f"{ORDER_USAGE_LOG_ACTION}: {order_info.user_name}, "
        f"{ORDER_USAGE_LOG_DATE_LABEL}: {order_date.strftime('%Y-%m-%d')}, "
        f"{ORDER_USAGE_LOG_FORM_LABEL}: {order_info.form_type}, "
        f"{ORDER_USAGE_LOG_OPERATOR_LABEL}: {cnun}, "
        f"{ORDER_USAGE_LOG_REMARK_LABEL}: {remark}, "
        f"{ORDER_USAGE_LOG_TYPE_LABEL}: {order_info.order_type}"
    )
    return {
        "usage_user_id": usage_user_id,
        "usage_user_name": cnun,
        "usage_menu": menu,
    }


def _cancel_usage_log_params(delete_info, cnun: str, usage_user_id: str) -> dict:
    menu = (
        f"{ORDER_USAGE_LOG_CANCEL_ACTION}: {delete_info.user_name}, "
        f"{ORDER_USAGE_LOG_DATE_LABEL}: {delete_info.start_date.strftime('%Y-%m-%d')}, "
        f"{ORDER_USAGE_LOG_TYPE_LABEL}: {delete_info.order_type}, "
        f"{ORDER_USAGE_LOG_OPERATOR_LABEL}: {cnun}"
    )
    return {
        "usage_user_id": usage_user_id,
        "usage_user_name": cnun,
        "usage_menu": menu,
    }


def submit_order(order_info):
    '''
    核心订饭逻辑
    :param order_info:
    :return:
    '''
    order_info.user_name = _ensure_user_exists(order_info.user_name)

    today = date.today()
    max_allowed_date = today + timedelta(days=30)
    now_time = datetime.now().time()  # 获取当前时间（时、分、秒）
    deadline = _get_order_deadline(order_info.order_type)
    includes_today = order_info.start_date <= today <= order_info.end_date
    if includes_today and not _is_hr_operator(order_info.operator) and now_time > deadline:
        raise HTTPException(
            status_code=403,
            detail=f"已超过今日{order_info.order_type}订餐截止时间({deadline.strftime('%H:%M')})，请联系人力部门处理。",
        )
    if order_info.start_date < date.today():
        raise HTTPException(status_code=400,detail="订餐时间不能小于今天")
    if order_info.end_date < order_info.start_date:
        raise HTTPException(status_code=400, detail="结束日期不能小于开始日期。")
    if (order_info.end_date - order_info.start_date).days > 14:
        raise HTTPException(status_code=400, detail="为了避免错误，开始日期、结束日期相差不能超过14天。")
    if order_info.end_date > max_allowed_date:
        raise HTTPException(status_code=400, detail="不能输入30天之后的日期。")

    duplicate_sql = """
    SELECT COUNT(*)
      FROM Lunch
     WHERE RiQi = %(riqi)s
       AND YongHu = %(user_name)s
       AND LeiXing = %(order_type)s
       AND YorN = 'Y'
    """
    insert_sql = """
    INSERT INTO Lunch(
        RiQi, YongHu, YorN, XingShi, CNUN, BaoMingShiJian,
        QuXiaoCNUN, QuXiaoShiJian, BeiZhu, LeiXing
    )
    VALUES (
        %(riqi)s, %(user_name)s, 'Y', %(form_type)s, %(cnun)s, %(baoming_time)s,
        '', '1900-01-01 00:00:00.000', %(remark)s, %(order_type)s
    );
    """
    usage_log_sql = """
    INSERT INTO dbo.CaiDanShiYongJiLu ([UserID], [UserName], [Menu], [Time])
    VALUES (%(usage_user_id)s, %(usage_user_name)s, %(usage_menu)s, GETDATE());
    """
    insert_with_usage_log_sql = f"{insert_sql}\n{usage_log_sql}"
    baoming_time = datetime.now()
    cnun = f"FeiShu@{order_info.operator}"
    usage_user_id = _get_order_usage_user_id(order_info.user_name)
    inserted_count = 0
    duplicate_messages = []
    dates_to_insert = []

    flag = order_info.start_date
    try:
        while flag <= order_info.end_date:
            exists_count = _db_select(duplicate_sql, {
                "riqi": flag,
                "user_name": order_info.user_name,
                "order_type": order_info.order_type,
            })
            if exists_count and int(exists_count) > 0:
                duplicate_messages.append(f"{order_info.user_name}在{flag}已经订饭{order_info.order_type}了，不能重复")
            else:
                dates_to_insert.append(flag)
            flag += timedelta(days=1)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"检查重复订饭失败：{exc}") from exc

    notification_recipient = None
    if _is_proxy_order(order_info) and dates_to_insert:
        notification_recipient = _get_email_recipient(order_info.user_name)

    try:
        for flag in dates_to_insert:
            params = {
                "riqi": flag,
                "user_name": order_info.user_name,
                "form_type": order_info.form_type,
                "cnun": cnun,
                "baoming_time": baoming_time,
                "remark": order_info.remark,
                "order_type": order_info.order_type,
            }
            params.update(_order_usage_log_params(order_info, flag, cnun, usage_user_id))
            _db_write(insert_with_usage_log_sql, params)
            inserted_count += 1
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"写入数据库失败：{exc}") from exc

    notification_sent = False
    if notification_recipient:
        try:
            notification_sent = _send_proxy_order_email(order_info, dates_to_insert, notification_recipient)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"发送代订饭通知失败：{exc}") from exc
        if not notification_sent:
            raise HTTPException(status_code=500, detail="发送代订饭通知失败。")

    return {
        "msg": "提交完成",
        "inserted_count": inserted_count,
        "inserted_dates": [str(d) for d in dates_to_insert],
        "duplicate_messages": duplicate_messages,
        "notification_sent": notification_sent,
    }



def check_order(user_name: str | None = None, start_date: date | None = None, end_date: date | None = None):
    '''
    查询订餐逻辑
    :param user_name:
    :param start_date:
    :param end_date:
    :return:
    '''
    where_parts = ["YorN = 'Y'"]
    params = {}

    if user_name:
        where_parts.append("YongHu = %(user_name)s")
        params["user_name"] = user_name

    if start_date and end_date:
        if end_date < start_date:
            raise HTTPException(status_code=400, detail="结束日期不能早于开始日期。")
        where_parts.append("RiQi BETWEEN %(start_date)s AND %(end_date)s")
        params["start_date"] = start_date
        params["end_date"] = end_date

    if not user_name and not (start_date and end_date):
        raise HTTPException(status_code=400, detail="请输入查询人，或同时选择开始日期和结束日期。")

    check_sql = f"""
    SELECT RiQi,XingShi,LeiXing,CNUN,BaoMingShiJian,YongHu
      FROM Lunch
     WHERE {' AND '.join(where_parts)}
     ORDER BY RiQi, YongHu, LeiXing
    """
    try:
        rows = DBtools.sf_db(check_sql, params)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"check order failed: {exc}") from exc
    return rows


def delete_order(delete_info):
    '''
    取消订餐逻辑
    :param delete_info:
    :return:
    '''
    delete_info.user_name = _ensure_user_exists(delete_info.user_name)

    today = date.today()
    if delete_info.start_date < today:
        raise HTTPException(status_code=403, detail="今天之前的订单不能取消。")

    if delete_info.start_date == today and not _is_hr_operator(delete_info.operator):
        deadline = _get_cancel_deadline(delete_info.order_type)
        if datetime.now().time() > deadline:
            raise HTTPException(
                status_code=403,
                detail=f"已超过今日{delete_info.order_type}取消截止时间({deadline.strftime('%H:%M')})，不能取消。",
            )

    notification_recipient = None
    if _is_proxy_action(delete_info.operator, delete_info.user_name):
        notification_recipient = _get_email_recipient(delete_info.user_name)

    exists_sql = """
    SELECT COUNT(*)
      FROM Lunch
     WHERE YongHu = %(user_name)s
       AND YorN = 'Y'
       AND RiQi = %(RiQi)s
       AND LeiXing = %(order_type)s
    """
    delete_sql = """
    UPDATE Lunch
    SET YorN = 'N',
        QuXiaoCNUN = %(operator)s,
        QuXiaoShiJian = GETDATE()
    WHERE YongHu = %(user_name)s
    AND YorN = 'Y'
    AND RiQi = %(RiQi)s
    AND LeiXing = %(order_type)s;
    """
    usage_log_sql = """
    INSERT INTO dbo.CaiDanShiYongJiLu ([UserID], [UserName], [Menu], [Time])
    VALUES (%(usage_user_id)s, %(usage_user_name)s, %(usage_menu)s, GETDATE());
    """
    delete_with_usage_log_sql = f"{delete_sql}\n{usage_log_sql}"
    cnun = f"FeiShu@{delete_info.operator}"
    usage_user_id = _get_order_usage_user_id(delete_info.user_name)
    param = {
        "operator": delete_info.operator,
        "user_name": delete_info.user_name,
        "RiQi": delete_info.start_date,
        "order_type": delete_info.order_type,
    }
    param.update(_cancel_usage_log_params(delete_info, cnun, usage_user_id))

    try:
        exists_count = _db_select(exists_sql, param)
        if int(exists_count or 0) <= 0:
            raise HTTPException(status_code=404, detail="未找到可取消的订单。")
        _db_write(delete_with_usage_log_sql, param)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code = 500,detail=f"取消失败{exc}") from exc

    notification_sent = False
    if notification_recipient:
        try:
            notification_sent = _send_proxy_cancel_email(delete_info, notification_recipient)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"发送代取消订饭通知失败：{exc}") from exc
        if not notification_sent:
            raise HTTPException(status_code=500, detail="发送代取消订饭通知失败。")

    return {
        "success": True,
        "message": "取消成功",
        "notification_sent": notification_sent,
    }

def update_order(update_info):
    '''
    修改订单逻辑
    :param update_info:
    :return:
    '''
    update_info.user_name = _ensure_user_exists(update_info.user_name)

    today = date.today()
    max_allowed_date = today + timedelta(days=30)
    if update_info.start_date < today:
        raise HTTPException(status_code=403, detail="修改时间不能小于今天")
    if update_info.end_date < update_info.start_date:
        raise HTTPException(status_code=400, detail="结束日期不能小于开始日期")
    if (update_info.end_date - update_info.start_date).days > 14:
        raise HTTPException(status_code=400, detail="为了避免错误，开始日期、结束日期相差不能超过14天。")
    if update_info.end_date > max_allowed_date:
        raise HTTPException(status_code=400, detail="不能输入30日之后的信息")

    includes_today = update_info.start_date <= today <= update_info.end_date
    if includes_today and not _is_hr_operator(update_info.operator):
        deadline = _get_order_deadline(update_info.order_type)
        if datetime.now().time() > deadline:
            raise HTTPException(
                status_code=403,
                detail=f"已经超出{update_info.order_type}的修改时间范围({deadline.strftime('%H:%M')})，请联系人力部门处理。",
            )

    exists_sql = """
    SELECT COUNT(*)
      FROM Lunch
     WHERE YongHu = %(user_name)s
       AND YorN = 'Y'
       AND RiQi = %(riqi)s
       AND LeiXing = %(order_type)s
    """
    update_sql = """
    UPDATE Lunch
       SET XingShi = %(form_type)s,
           CNUN = %(operator)s,
           BaoMingShiJian = GETDATE()
     WHERE YongHu = %(user_name)s
       AND YorN = 'Y'
       AND RiQi = %(riqi)s
       AND LeiXing = %(order_type)s
    """

    updated_count = 0
    updated_dates = []
    missing_dates = []
    flag = update_info.start_date
    try:
        while flag <= update_info.end_date:
            params = {
                "operator": f"FeiShu@{update_info.operator}",
                "user_name": update_info.user_name,
                "riqi": flag,
                "order_type": update_info.order_type,
                "form_type": update_info.form_type,
            }
            exists_count = _db_select(exists_sql, params)
            if int(exists_count or 0) <= 0:
                missing_dates.append(str(flag))
            else:
                rowcount = _db_write(update_sql, params)
                updated_count += rowcount if rowcount and rowcount > 0 else 1
                updated_dates.append(flag)
            flag += timedelta(days=1)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"修改失败{exc}") from exc

    if updated_count <= 0:
        raise HTTPException(status_code=404, detail="未找到可修改的订单")

    notification_sent = False
    if _is_proxy_action(update_info.operator, update_info.user_name):
        try:
            notification_recipient = _get_email_recipient(update_info.user_name)
            notification_sent = _send_proxy_update_email(update_info, updated_dates, notification_recipient)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"发送代修改订饭通知失败：{exc}") from exc
        if not notification_sent:
            raise HTTPException(status_code=500, detail="发送代修改订饭通知失败。")

    return {
        "success": True,
        "message": "修改成功",
        "updated_count": updated_count,
        "missing_dates": missing_dates,
        "notification_sent": notification_sent,
    }
