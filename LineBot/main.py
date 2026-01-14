from itertools import product
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration, ApiClient, ImageMessage, MessagingApi, ReplyMessageRequest, TextMessage, StickerMessage, ImageMessage, Emoji, PushMessageRequest
from linebot.v3.exceptions import InvalidSignatureError
from linebot.webhook import MessageEvent, JoinEvent, FollowEvent
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import os
import time
from googleapiclient import http
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from httplib2 import Http
from oauth2client import file, client, tools
from random import randint
from flask_restful import Resource, Api
import gspread
from oauth2client.service_account import ServiceAccountCredentials as sac
import datetime as dt
import pytz
import threading
from time import sleep
# from youtube_search import YoutubeSearch
from youtube_utils import CustomYoutubeSearch
from json import dump, load
import re
# from revChatGPT.V1 import Chatbot 

Debug_Mode = False
app = Flask(__name__)
# line api 基本資訊
configuration = Configuration(access_token = os.environ["ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["SECRET"])
# google drive(oauth2) 權限
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
# OK Stickers
ok_sticker = [["6362", "11087920"], ["8525", "16581290"], ["11539", "52114113"]]
# 雲端文件存放位置
folder_id = "1xgbysfK5zTz1CLDeKZaMiuG1HiNS8G4S"
folder_url = "https://drive.google.com/folderview?id=1xgbysfK5zTz1CLDeKZaMiuG1HiNS8G4S"
# 記帳相關資料
auth_json = "autoupload-336306-711b168145e6.json"
gs_scopes = ["https://spreadsheets.google.com/feeds"]
spreadsheet_key = "1MfgcbA0lW58HaFYFsogG86jXCVDj2RLzT0_LSZcKm_w"
muan_spreadsheet_key = "1DD5pvHvoYi5hYhSEVkdjzddX-GaobnrJxO6Hpl8wxv4"
gorden_spreadsheet_key = "1L7FQE54CD88DP0y-2Wqir1VkPoK-B34Z2E7H7LIpb7c"
setting_sheet_key = "1VzaD8kM0H7IE9cybKiRUhOOo3Z7njlhwELFJCm07YQc"
my_user_id = "U3e5359d656fc6d1d6610ddcb33323bde"
muan_user_id = "U56745f8381f264a269dbca24eb4c6977"
gorden_user_id = "U01f7154cb1cb9638a364157d03a0d932"
mom_user_id = "U587c68afa4b2167d47d76d72dcd7a0d3"
CONFIG_PATH = 'region.json'
bible_group_id = "Cbbf8bfb6f0e42e94f6d2edcfd6e231cd"


# line bot 初始化
@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print(
            "Invalid signature. Please check your channel access token/channel secret."
        )
        abort(400)

    return 'OK'


# 將檔案上傳至google drive
def upload_file(fileName, path):
    value = {"success": True, "fileURL": ""}
    # 取得認證
    store = file.Storage("token.json")
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets("credentials.json", SCOPES)
        creds = tools.run_flow(flow, store)

    service = build("drive", "v3", http = creds.authorize(Http()),  static_discovery=False)
    print("開始上傳檔案")
    start = time.time()
    file_metada = {"name": fileName, "parents": [folder_id]}
    media = MediaFileUpload(path, )
    try:
        file_content = service.files().create(body = file_metada, media_body = media, fields = "id").execute() # 上傳檔案
        id = file_content.get("id")
        service.permissions().create(body={"role": "reader", "type": "anyone"}, fileId = id).execute() # 開啟共用
        end = time.time()
        print("完成")
        print("上傳時間:", end - start, "s")
        print(f"https://drive.google.com/file/d/{id}/view")
        value["fileURL"] =  f"https://drive.google.com/file/d/{id}/view"
    except:
        value["success"] = False
    return value


# 檢查來源是否正確 獲取傳送對象
def From():
    l = []
    with open(os.path.join("info", "from.txt"), "r") as f:
        for i in f:
            l.append(i.strip("\n"))
    return l
def To():
    l = []
    with open(os.path.join("info", "to.txt"), "r") as f:
        for i in f:
            l.append(i.strip("\n"))
    return l
def Can_Send(event):
    if event.source.type == "group" and event.source.group_id in From(): return True
    return False



# 記帳相關
# 確保兩個工作表存在
def init_region_sheet():
    # 認證
    cr = sac.from_json_keyfile_name(auth_json)
    gs_client = gspread.authorize(cr)
    ss = gs_client.open_by_key(setting_sheet_key)
    try:
        sheet = ss.worksheet("Regions")
    except gspread.exceptions.WorksheetNotFound:
        sheet = ss.add_worksheet(title="Regions", rows=100, cols=2)
        sheet.append_row(['region_name', 'timezone'])
    return sheet

def init_user_region_sheet():
    cr = sac.from_json_keyfile_name(auth_json)
    gs_client = gspread.authorize(cr)
    ss = gs_client.open_by_key(setting_sheet_key)
    try:
        sheet = ss.worksheet("User Regions")
    except gspread.exceptions.WorksheetNotFound:
        sheet = ss.add_worksheet(title="User Regions", rows=100, cols=3)
        sheet.append_row(['user_id', 'region_name', 'timezone'])
    return sheet

# 新增地區對應時區
def add_new_region(region_name, timezone_str):
    region_name = region_name.replace("台", "臺") # 統一用「臺」而非「台」
    try:
        pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        raise ValueError(f'不合法的時區：{timezone_str}')
    sheet = init_region_sheet()
    regs = sheet.get_all_records()
    for r in regs:
        if r['region_name'] == region_name:
            sheet.update_cell(regs.index(r) + 2, 2, timezone_str)
            return
    sheet.append_row([region_name, timezone_str])

# 設定使用者地區
def set_user_region(user_id, region_name):
    region_name = region_name.replace("台", "臺") # 統一用「臺」而非「台」
    region_sheet = init_region_sheet()
    user_sheet = init_user_region_sheet()
    regions = region_sheet.get_all_records()
    tz = None
    for r in regions:
        if r['region_name'] == region_name:
            tz = r['timezone']
            break
    if tz is None:
        raise KeyError(f'地區 {region_name} 尚未註冊，請先使用「新增地區 <地區名稱> <時區字串>」指令。')
    users = user_sheet.get_all_records()
    for idx, r in enumerate(users, start=2):
        if r['user_id'] == user_id:
            user_sheet.update_cell(idx, 2, region_name)
            user_sheet.update_cell(idx, 3, tz)
            return
    user_sheet.append_row([user_id, region_name, tz])

# 取得使用者設定
def get_user_setting(user_id):
    user_sheet = init_user_region_sheet()
    users = user_sheet.get_all_records()
    for r in users:
        if r['user_id'] == user_id:
            return r['region_name'], r['timezone']
    region_sheet = init_region_sheet()
    regions = region_sheet.get_all_records()
    for r in regions:
        if r['region_name'] == '臺灣':
            return '臺灣', r['timezone']
    return '臺灣', 'ROC'


# 記帳
def track_expense(l, user_id):
    # 認證
    cr = sac.from_json_keyfile_name(auth_json)
    gs_client = gspread.authorize(cr)
    # 抓取現在地區、時區、時間
    region, tz_str = get_user_setting(user_id)
    now = dt.datetime.now(pytz.timezone(tz_str))
    # 另外補齊分鐘的0
    if now.minute < 10:
        minute = "0" + str(now.minute)
    else:
        minute = now.minute
    # 開啟試算表
    if user_id == my_user_id:
        sheet = gs_client.open_by_key(spreadsheet_key)
        person = "沐恩"
    elif user_id == muan_user_id:
        sheet = gs_client.open_by_key(muan_spreadsheet_key)
        person = "沐安"
    elif user_id == gorden_user_id:
        sheet = gs_client.open_by_key(gorden_spreadsheet_key)
        person = "鐙振"
    # 判別是否為爸媽的錢
    if ((len(l) > 2 and l[2] == "爸媽") or len(l) == 2) and (user_id == my_user_id or user_id == muan_user_id):
        is_parent = 1
        wks_name = "爸媽的錢"
    else:
        is_parent = 0
        if region != "臺灣" and region != "台灣":
            wks_name = f"{str(now.year)} {region}"
        else:
            wks_name = f"{str(now.year)}/{str(now.month)}"
    try:
        wks = sheet.worksheet(wks_name)
        new_sheet = 0
    except:
        # 建立新workbook
        wks = sheet.add_worksheet(wks_name, 0, 0)
        new_sheet = 1
        row_value = ["日期", "時間", "類別", "項目", "收入", "支出", "總計", "備註"]
        wks.append_row(row_value)
    # 判別收入或支出
    if l[0].replace(".", "").isdigit(): # 收入
        if is_parent: row_value = [f"{now.month}/{now.day}", f"{now.hour}:{minute}", l[1], l[0], ""]
        else: row_value = [f"{now.month}/{now.day}", f"{now.hour}:{minute}", l[2], l[1], l[0], ""]
    else: # 支出
        if is_parent: row_value = [f"{now.month}/{now.day}", f"{now.hour}:{minute}", l[0], "", l[1]]
        else: row_value = [f"{now.month}/{now.day}", f"{now.hour}:{minute}", l[2], l[0], "", l[1]]
    # 加入新資料
    all_data = wks.get_all_values()
    # 行數
    length = len(all_data)
    # 計算總和
    if length == 1:
        if is_parent: row_value.append(f"=SUM(D{length + 1}, -E{length + 1})")
        else: row_value.append(f"=SUM(E{length + 1}, -F{length + 1})")
    else:
        if is_parent: row_value.append(f"=SUM(D{length + 1}, -E{length + 1}, F{length})")
        else: row_value.append(f"=SUM(E{length + 1}, -F{length + 1}, G{length})")
    # 加上備註
    if len(l) == 4: row_value.append(l[3])
    wks.append_row(row_value, value_input_option="USER_ENTERED")
    # 回傳剩餘金額
    all_data = wks.get_all_values()
    if is_parent: lst = all_data[-1][5]
    else: lst = all_data[-1][6]

    # 創建 Pivot table(如果需要的話)
    try:
        pivot_wks = sheet.worksheet(wks_name + " 樞紐分析表")
    except:
        pivot_wks = sheet.add_worksheet(wks_name + " 樞紐分析表", 0, 0)
        # 定義樞紐表的配置
        pivot_table_request = {
            "updateCells": {
                "rows": {
                    "values": [
                        {
                            "pivotTable": {
                                "source": {
                                    "sheetId": wks.id,
                                    "startRowIndex": 0,
                                    "startColumnIndex": 0,
                                    "endRowIndex": 1000,  # 根據您的數據範圍進行調整
                                    "endColumnIndex": 7
                                },
                                "rows": [
                                    {
                                        "sourceColumnOffset": 2,
                                        "showTotals": True,
                                        "sortOrder": "ASCENDING"
                                    },
                                    {
                                        "sourceColumnOffset": 0,
                                        "showTotals": True,
                                        "sortOrder": "ASCENDING"
                                    },
                                    {
                                        "sourceColumnOffset": 3,
                                        "showTotals": False,
                                        "sortOrder": "ASCENDING"
                                    }
                                ],
                                "columns": [],
                                "values": [
                                    {
                                        "summarizeFunction": "SUM",
                                        "formula": "='收入' - '支出'",  # 使用自定義公式
                                        "name": "金額"
                                    }
                                ],
                                "valueLayout": "HORIZONTAL"
                            }
                        }
                    ]
                },
                "start": {
                    "sheetId": pivot_wks.id,
                    "rowIndex": 0,
                    "columnIndex": 0
                },
                "fields": "pivotTable"
            }
        }

        # 添加樞紐表到試算表中
        body = {
            "requests": [
                pivot_table_request
            ]
        }

        sheet.batch_update(body)

    # 回傳資料給媽媽
    if is_parent:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            # 判別收入或支出
            if l[0].isdigit():
                line_bot_api.push_message_with_http_info(
                    PushMessageRequest(
                        to=mom_user_id,
                        messages=[
                            TextMessage(text=f"{person}增加了{int(l[0])}，目前剩餘{lst}元")
                        ]
                    )
                )
            else:
                if int(lst) <= 0:
                    line_bot_api.push_message_with_http_info(
                        PushMessageRequest(
                            to=mom_user_id,
                            messages=[
                                TextMessage(text=f"{person}購買了{l[0]}，花了{l[1]}元，剩餘{lst}元"),
                                TextMessage(
                                    text=f"$目前{person}的錢不足，請記得再補充！",
                                    emojis=[Emoji(index=0, product_id="5ac1bfd5040ab15980c9b435", emoji_id="010")]),
                                # https://developers.line.biz/en/docs/messaging-api/sticker-list/#sticker-definitions
                                StickerMessage(package_id="8525", sticker_id="16581307")
                            ]
                        )
                    )
                else:
                    line_bot_api.push_message_with_http_info(
                        PushMessageRequest(
                            to=mom_user_id,
                            messages=[
                                TextMessage(text=f"{person}購買了{l[0]}，花了{l[1]}元，剩餘{lst}元"),
                            ]
                        )
                    )

    return lst


# 清除最後一筆記帳紀錄
def clear_last_entry(user_id, is_parent):
    # 認證
    cr = sac.from_json_keyfile_name(auth_json)
    gs_client = gspread.authorize(cr)
    # 抓取現在地區、時區、時間
    region, tz_str = get_user_setting(user_id)
    now = dt.datetime.now(pytz.timezone(tz_str))
    # 開啟試算表
    if user_id == my_user_id:
        sheet = gs_client.open_by_key(spreadsheet_key)
    elif user_id == muan_user_id:
        sheet = gs_client.open_by_key(muan_spreadsheet_key)
    elif user_id == gorden_user_id:
        sheet = gs_client.open_by_key(gorden_spreadsheet_key)
    # 判別是否為爸媽的錢
    if is_parent:
        wks_name = "爸媽的錢"
    else:
        # 判斷是否為出國模式
        if region != "臺灣":
            wks_name = f"{str(now.year)} {region}"
        else:
            wks_name = f"{str(now.year)}/{str(now.month)}"
    pivot_name = wks_name + ' 樞紐分析表'
    # 嘗試刪除最後一列
    try:
        wks = sheet.worksheet(wks_name)
        values = wks.get_all_values()
        # 有資料：刪除最後一行
        if len(values) > 1:
            last_row = values[-1]
            # 項目名稱位置依據你的表格格式調整
            if is_parent:
                item_name = last_row[2]
            else:
                item_name = last_row[3]
            wks.delete_rows(len(values))
            # 再次確認是否只剩標題列
            if len(wks.get_all_values()) <= 1:
                sheet.del_worksheet(wks)
                try:
                    pivot_wks = sheet.worksheet(pivot_name)
                    sheet.del_worksheet(pivot_wks)
                except:
                    pass
            return item_name
        # 無資料：直接刪除該工作表
        else:
            sheet.del_worksheet(wks)
            try:
                pivot_wks = sheet.worksheet(pivot_name)
                sheet.del_worksheet(pivot_wks)
            except:
                pass
            return None
    except:
        return None

# def gpt_response(gpt_prompt):
#     openai.api_key = os.environ["OPENAI_API_KEY"]
#     response = openai.Completion.create(
#         # engine = "text-curie-001",
#         engine = "text-davinci-002",
#         prompt = gpt_prompt,
#         temperature=0.9,
#         max_tokens=2000,
#         top_p=0.5,
#         frequency_penalty=0.0,
#         presence_penalty=0.0,
#         # stop=["\n"]
#     )
#     return response["choices"][0]["text"][2:]

# def gpt_response_web(gpt_prompt):
#     chatbot = Chatbot(config={
#         "access_token": os.environ["ChatGPT_Access_Token"]
#     })
#     response = ""
#     for data in chatbot.ask(gpt_prompt):
#         response = data["message"]
#     return response


# 取得今日陪你讀聖經連結
def send_bible():
    current_date = dt.datetime.now(pytz.timezone("Asia/Taipei"))
    start_date = dt.datetime(2022, 6, 9, tzinfo=pytz.timezone("Asia/Taipei"))
    with open("bible.json", "r", encoding="utf-8") as f:
        d = load(f)
    keyword = d[(current_date - start_date).days % len(d)]

    result = CustomYoutubeSearch("陪你讀聖經3 " + keyword, max_results=5).to_dict()

    for video in result:
        title = video["title"]
        if "陪你讀聖經3" in title and keyword in title:
            video_url = "https://youtu.be/watch?v=" + video["id"]
            print(video_url)
            return f"{current_date.strftime('%Y/%m/%d')} {keyword}\n{video_url}"
    # return f"{current_date.strftime('%Y/%m/%d')} {keyword}\nhttps://youtu.be/watch?v={result[0]['id']}"
    return f"{current_date.strftime('%Y/%m/%d')} {keyword}\n找不到符合的影片連結\n{result[0]['title']}"

# 讀取當天跑步資訊
def get_today_run_info():
    # 載入更新後的課表
    with open("run_schedule.json", "r", encoding="utf-8") as f:
        schedule = load(f)
    today = dt.datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d")
    if today in schedule:
        distance, pace = schedule[today]
        if distance == "休息/交叉訓練":
            return f"今天是休息日或交叉訓練，記得放鬆一下！"
        else:
            return f"今日課表：{distance}\n配速：{pace}"
    else:
        return "今天沒有安排跑步課表喔！"


# 讀取明天跑步資訊
def get_tomorrow_run_info():
    with open("run_schedule.json", "r", encoding="utf-8") as f:
        schedule = load(f)
    tomorrow = (dt.datetime.now(pytz.timezone("Asia/Taipei")) + dt.timedelta(days=1)).strftime("%Y-%m-%d")
    if tomorrow in schedule:
        distance, pace = schedule[tomorrow]
        if "休息" in distance:
            return f"明天是休息日或交叉訓練，記得放鬆一下！"
        else:
            return f"明日課表：{distance}\n配速：{pace}"
    else:
        return "明天沒有安排跑步課表喔！"




def get_message_content(message_id, save_path):
    # LINE Messaging API 的端點
    url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
    # 設定標頭，包含身份驗證的 Channel Access Token
    headers = {
        "Authorization": f"Bearer {os.environ['ACCESS_TOKEN']}"
    }
    try:
        # 發送 GET 請求
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()  # 如果回應碼不是 200，會引發例外

        # 將內容儲存到本地檔案
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)

        print(f"檔案已成功儲存至：{save_path}")
    except requests.exceptions.RequestException as e:
        print(f"取得訊息內容失敗：{e}")


@handler.add(MessageEvent)
def handle_message(event):
    print(event)
    with ApiClient(configuration) as api_client:
        # 取得 line bot api
        line_bot_api = MessagingApi(api_client)

        # 忽略高中班群訊息
        if event.source.type == "group" and event.source.group_id == "Ccea56b432a88c91e8ae50f7399dfdc77": return
        # 處理文字訊息
        if event.message.type == "text":
            if event.message.text[:2] == "早安":
                pic = f"https://www.crazybless.com/good-morning/morning/image/%E6%97%A9%E5%AE%89%E5%9C%96%E4%B8%8B%E8%BC%89%20({randint(1, 1477)}).jpg"
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[ImageMessage(original_content_url=pic, preview_image_url=pic)]
                    )
                )
            elif "好電" in event.message.text:
                # 取得使用者名稱
                if event.source.type == "group":
                    profile = line_bot_api.get_group_member_profile(event.source.group_id, event.source.user_id)
                else:
                    profile = line_bot_api.get_profile(event.source.user_id)
                # 傳送訊息
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(
                            text=str(profile.display_name) + "好電⚡",
                            quote_token=event.message.quote_token
                        )]
                    )
                )
            elif event.message.text[:2] == "聖經":
                msg = send_bible()
                # 找不到影片連結
                if "找不到符合的影片連結" in msg:
                    line_bot_api.push_message_with_http_info(
                        PushMessageRequest(
                            to=my_user_id,
                            messages=[
                                TextMessage(text=msg)
                            ]
                        )
                    )
                else:
                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(
                                text=msg,
                                quote_token=event.message.quote_token
                            )]
                        )
                    )

            elif event.source.type == "user":
                # 記帳
                if event.source.user_id == my_user_id or event.source.user_id == muan_user_id or event.source.user_id == gorden_user_id:
                    l = list(event.message.text.split())
                    if l[0].replace(".", "").isdigit() or (len(l) > 1 and l[1].replace(".", "").isdigit()):
                        lst = track_expense(l, event.source.user_id)
                        line_bot_api.reply_message_with_http_info(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[
                                    TextMessage(
                                        text=f"記帳完成！$剩餘{lst}元", 
                                        emojis = [Emoji(index=5, product_id="5ac1bfd5040ab15980c9b435", emoji_id="009")],
                                        quote_token=event.message.quote_token
                                    )
                                ]
                            )
                        )
                    # 新增地區指令
                    elif l[0] == "新增地區":
                        # 輸入格式錯誤
                        if(len(l) != 3):
                            line_bot_api.reply_message_with_http_info(
                                ReplyMessageRequest(
                                    reply_token=event.reply_token,
                                    messages=[
                                        TextMessage(
                                            text="格式錯誤！$請用「新增地區 <地區名稱> <時區字串>」", 
                                            emojis = [Emoji(index=5, product_id="5ac1bfd5040ab15980c9b435", emoji_id="013")],
                                            quote_token=event.message.quote_token
                                        )
                                    ]
                                )
                            )
                        else:
                            region_name, tz_str = l[1], l[2]
                            try: # 嘗試新增
                                add_new_region(region_name, tz_str)
                                line_bot_api.reply_message_with_http_info(
                                    ReplyMessageRequest(
                                        reply_token=event.reply_token,
                                        messages=[
                                            TextMessage(
                                                text=f"新增成功！${region_name}的對應時區為{tz_str}", 
                                                emojis = [Emoji(index=5, product_id="5ac1bfd5040ab15980c9b435", emoji_id="021")],
                                                quote_token=event.message.quote_token
                                            )
                                        ]
                                    )
                                )
                            except: # 無法新增
                                line_bot_api.reply_message_with_http_info(
                                    ReplyMessageRequest(
                                        reply_token=event.reply_token,
                                        messages=[
                                            TextMessage(
                                                text="新增失敗！$請檢查資訊或格式是否正確", 
                                                emojis = [Emoji(index=5, product_id="5ac1bfd5040ab15980c9b435", emoji_id="024")],
                                                quote_token=event.message.quote_token
                                            )
                                        ]
                                    )
                                )

                    elif l[0] == "地區":
                        if len(l) != 2:
                            line_bot_api.reply_message_with_http_info(
                                ReplyMessageRequest(
                                    reply_token=event.reply_token,
                                    messages=[
                                        TextMessage(
                                            text="格式錯誤！$請用「地區 <地區名稱>」", 
                                            emojis = [Emoji(index=5, product_id="5ac1bfd5040ab15980c9b435", emoji_id="013")],
                                            quote_token=event.message.quote_token
                                        )
                                    ]
                                )
                            )
                        else:
                            region_name = l[1]
                            try:
                                set_user_region(event.source.user_id, l[1])
                                line_bot_api.reply_message_with_http_info(
                                    ReplyMessageRequest(
                                        reply_token=event.reply_token,
                                        messages=[
                                            TextMessage(
                                                text=f"設定成功！$目前地區為{region_name}", 
                                                emojis = [Emoji(index=5, product_id="5ac1bfd5040ab15980c9b435", emoji_id="021")],
                                                quote_token=event.message.quote_token
                                            )
                                        ]
                                    )
                                )
                            except:
                                line_bot_api.reply_message_with_http_info(
                                    ReplyMessageRequest(
                                        reply_token=event.reply_token,
                                        messages=[
                                            TextMessage(
                                                text=f"設定失敗！$地區 {region_name} 尚未註冊，請先使用「新增地區 <地區名稱> <時區字串>」指令", 
                                                emojis = [Emoji(index=5, product_id="5ac1bfd5040ab15980c9b435", emoji_id="024")],
                                                quote_token=event.message.quote_token
                                            )
                                        ]
                                    )
                                )
                    elif l[0] == "清除":
                        if not (len(l) == 1) and not (len(l) == 2 and l[1] == "爸媽"):
                            line_bot_api.reply_message_with_http_info(
                                ReplyMessageRequest(
                                    reply_token=event.reply_token,
                                    messages=[
                                        TextMessage(
                                            text=f"清除失敗！$請檢查格式是否正確", 
                                            emojis = [Emoji(index=5, product_id="5ac1bfd5040ab15980c9b435", emoji_id="024")],
                                            quote_token=event.message.quote_token
                                        )
                                    ]
                                )
                            )
                        else:
                            res = clear_last_entry(event.source.user_id, (len(l) == 2))
                            if res:
                                line_bot_api.reply_message_with_http_info(
                                    ReplyMessageRequest(
                                        reply_token=event.reply_token,
                                        messages=[
                                            TextMessage(
                                                text=f"清除成功！$已移除項目：{res}", 
                                                emojis = [Emoji(index=5, product_id="5ac1bfd5040ab15980c9b435", emoji_id="008")],
                                                quote_token=event.message.quote_token
                                            )
                                        ]
                                    )
                                )
                            else:
                                line_bot_api.reply_message_with_http_info(
                                    ReplyMessageRequest(
                                        reply_token=event.reply_token,
                                        messages=[
                                            TextMessage(
                                                text=f"清除失敗！$目前該工作表上沒有記帳紀錄", 
                                                emojis = [Emoji(index=5, product_id="5ac1bfd5040ab15980c9b435", emoji_id="010")],
                                                quote_token=event.message.quote_token
                                            )
                                        ]
                                    )
                                )
                    elif event.message.text == "跑步":
                        line_bot_api.reply_message_with_http_info(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=get_today_run_info())]
                            )
                        )
                    elif event.message.text == "明天跑步":
                        line_bot_api.reply_message_with_http_info(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=get_tomorrow_run_info())]
                            )
                        )
                    else:
                        line_bot_api.reply_message_with_http_info(
                            ReplyMessageRequest(
                                reply_token=event.reply_token,
                                messages=[TextMessage(text=event.message.text)]
                            )
                        )
                else:
                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=event.message.text)]
                        )
                    )

        if event.message.type == "image":
            get_message_content(str(event.message.id), os.path.join("storage", "temp.jpg"))
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="圖片已儲存")]
                )
            )
        # elif event.message.type == "file":
        #     print(event.message.id)
        #     if Debug_Mode or Can_Send(event):
        #         fileName = event.message.file_name
        #         get_message_content(str(event.message.id), os.path.join("storage", fileName))
        #         value = upload_file(fileName, os.path.join("storage", fileName))
        #         if value["success"] == False:
        #             try: 
        #                 line_bot_api.push_message_with_http_info(
        #                     PushMessageRequest(
        #                         to="U3e5359d656fc6d1d6610ddcb33323bde",
        #                         messages=[TextMessage(text="Token已過期 請盡速更新並重新傳檔案")]
        #                     )
        #                 )
        #             except:
        #                 pass
        #         else:
        #             to = To()
        #             fileURL = value["fileURL"]
        #             try:                
        #                 for i in to:
        #                     line_bot_api.push_message(
        #                         PushMessageRequest(
        #                             to=i,
        #                             messages=[TextMessage(text="大家好，我是物理小老師的機器人\n以下是老師要傳給同學的檔案：\n" + fileURL + "\n其他檔案：\n" + folder_url)]
        #                         )
        #                     )
        #                 sticker = ok_sticker[randint(0, 2)]
        #             except:
        #                 pass
        #             line_bot_api.reply_message_with_http_info(
        #                 ReplyMessageRequest(
        #                     reply_token=event.reply_token,
        #                     messages=[StickerMessage(package_id = sticker[0], sticker_id = sticker[1])]
        #                 )
        #             )

@handler.add(JoinEvent)
def handle_join(event):
    print(event)
    with ApiClient(configuration) as api_client:
        # 取得 line bot api
        line_bot_api = MessagingApi(api_client)
        with open(os.path.join("info", "group.txt"), "a") as f:
            content = line_bot_api.get_group_summary(event.source.group_id)
            f.write(content.group_name + " " + content.group_id + "\n")

@handler.add(FollowEvent)
def handler_follow(event):
    print(event)
    with ApiClient(configuration) as api_client:
        # 取得 line bot api
        line_bot_api = MessagingApi(api_client)
        with open(os.path.join("info", "user.txt"), "a") as f:
            content = line_bot_api.get_profile(event.source.user_id)
            f.write(content.display_name + " " + content.user_id + "\n")    

@app.route("/")
def running():
    return "running"

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0")
        print("start running!")
    except:
        os.system("kill 1")
