from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextSendMessage, ImageSendMessage, StickerSendMessage, FollowEvent, JoinEvent
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
# from revChatGPT.V1 import Chatbot 

Debug_Mode = False
app = Flask(__name__)
# line api 基本資訊
line_bot_api = LineBotApi(os.environ["ACCESS_TOKEN"])
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
my_user_id = "U3e5359d656fc6d1d6610ddcb33323bde"
muan_user_id = "U56745f8381f264a269dbca24eb4c6977"
mom_user_id = "U587c68afa4b2167d47d76d72dcd7a0d3"


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

# 取得長輩圖連結
def send_picture():
    r = requests.get("https://www.crazybless.com/good-morning/")
    soup = BeautifulSoup(r.text, "html.parser")
    result = str(soup.find(class_="qqwe").attrs["src"])
    # 將網址轉換成utf-8
    pic = quote(result.encode('utf8')).replace("%3A", ":")
    print(pic)
    return pic

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


# 記帳
def track_expense(l, user_id):
    # 認證
    cr = sac.from_json_keyfile_name(auth_json)
    gs_client = gspread.authorize(cr)
    # 抓取現在時間
    now = dt.datetime.now(pytz.timezone("Asia/Taipei"))
    foreign_mode = 0
    # 是否為外國記帳模式
    if now.month == 7 and now.day >= 27 and now.day <= 31:
        foreign_mode = 1
        # now = dt.datetime.now(pytz.timezone("Asia/Kuala_Lumpur"))
    # 另外補齊分鐘的0
    if now.minute < 10:
        minute = "0" + str(now.minute)
    else:
        minute = now.minute
    # 開啟試算表
    if user_id == my_user_id:
        sheet = gs_client.open_by_key(spreadsheet_key)
        person = "沐恩"
    else:
        sheet = gs_client.open_by_key(muan_spreadsheet_key)
        person = "沐安"
    # 判別是否為爸媽的錢
    if (len(l) > 2 and l[2] == "爸媽") or len(l) == 2:
        is_parent = 1
        wks_name = "爸媽的錢"
    else:
        is_parent = 0
        if foreign_mode:
            wks_name = "2024/7大陸行"
        else:
            wks_name = f"{str(now.year)}/{str(now.month)}"
    try:
        wks = sheet.worksheet(wks_name)
        new_sheet = 0
    except:
        # 建立新workbook
        wks = sheet.add_worksheet(wks_name, 0, 0)
        new_sheet = 1
        row_value = ["日期", "時間", "類別", "項目", "收入", "支出", "總計"]
        wks.append_row(row_value)
    # 判別收入或支出
    if l[0].replace(".", "").isdigit():
        if is_parent: row_value = [f"{now.month}/{now.day}", f"{now.hour}:{minute}", l[1], l[0], ""]
        else: row_value = [f"{now.month}/{now.day}", f"{now.hour}:{minute}", l[2], l[1], l[0], ""]
    else:
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
    wks.append_row(row_value, value_input_option="USER_ENTERED")
    # 回傳剩餘金額
    all_data = wks.get_all_values()
    lst = all_data[-1][-1]

    # 創建 Pivot table(如果需要的話)
    if new_sheet:
        try:
            pivot_wks = sheet.worsheet(wks_name + " 樞紐分析表")
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
        # 判別收入或支出
        if l[0].isdigit():
            line_bot_api.push_message(mom_user_id, TextSendMessage(f"{person}增加了{int(l[0])}，目前剩餘{lst}元"))
        else:
            line_bot_api.push_message(mom_user_id, TextSendMessage(f"{person}購買了{l[0]}，花了{l[1]}元，剩餘{lst}元"))
    return lst
    

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



@handler.add(MessageEvent)
def handle_message(event):
    print(event)
    if event.source.type == "group" and event.source.group_id == "Ccea56b432a88c91e8ae50f7399dfdc77": return
    if event.message.type == "text":
        if event.message.text[:2] == "早安":
            pic = send_picture()
            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(original_content_url=pic, preview_image_url=pic))
        elif "好電" in event.message.text:
            if event.source.type == "group":
                profile = line_bot_api.get_group_member_profile(event.source.group_id, event.source.user_id)
            else:
                profile = line_bot_api.get_profile(event.source.user_id)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(str(profile.display_name) + "好電⚡"))
            
        elif event.source.type == "user":
            # 記帳
            if event.source.user_id == my_user_id or event.source.user_id == muan_user_id:
                l = list(event.message.text.split())
                if l[0].replace(".", "").isdigit() or (len(l) > 1 and l[1].replace(".", "").isdigit()):
                    lst = track_expense(l, event.source.user_id)
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text = f"記帳完成!剩餘{lst}元"))
                else:
                   # line_bot_api.reply_message(
                   #  event.reply_token,                TextSendMessage(text=gpt_response_web(event.message.text))) 
                    line_bot_api.reply_message(
                event.reply_token,                TextSendMessage(text=event.message.text))
            else:
                # line_bot_api.reply_message(
                # event.reply_token,                TextSendMessage(text=gpt_response_web(event.message.text))) 
                line_bot_api.reply_message(
                event.reply_token,                 TextSendMessage(text=event.message.text))
            
    if event.message.type == "image":
        content = line_bot_api.get_message_content(event.message.id)
        with open(os.path.join("storage", "temp.jpg"), "wb") as f:
            for chunk in content.iter_content():
                f.write(chunk)
    elif event.message.type == "file":
        print(event.message.id)
        if Debug_Mode or Can_Send(event):
            content = line_bot_api.get_message_content(str(event.message.id))
            fileName = event.message.file_name
            with open(os.path.join("storage", fileName), "wb") as f:
                for chunk in content.iter_content():
                    f.write(chunk)
            value = upload_file(fileName, os.path.join("storage", fileName))
            if value["success"] == False:
                try: 
                    line_bot_api.push_message("U3e5359d656fc6d1d6610ddcb33323bde", TextSendMessage("Token已過期 請盡速更新並重新傳檔案"))
                except:
                    pass
            else:
                to = To()
                fileURL = value["fileURL"]
                try:                
                    for i in to:
                        line_bot_api.push_message(i, TextSendMessage("大家好，我是物理小老師的機器人\n以下是老師要傳給同學的檔案：\n" + fileURL + "\n其他檔案：\n" + folder_url))
                    sticker = ok_sticker[randint(0, 2)]
                except:
                    pass
                line_bot_api.reply_message(event.reply_token, StickerSendMessage(sticker[0], sticker[1]))

@handler.add(JoinEvent)
def handle_join(event):
    print(event)
    with open(os.path.join("info", "group.txt"), "a") as f:
        content = line_bot_api.get_group_summary(event.source.group_id)
        f.write(content.group_name + " " + content.group_id + "\n")

@handler.add(FollowEvent)
def handler_follow(event):
    print(event)
    with open(os.path.join("info", "user.txt"), "a") as f:
        content = line_bot_api.get_profile(event.source.user_id)
        f.write(content.display_name + " " + content.user_id + "\n")    

@app.route("/")
def running():
    return "running"

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0")
    except:
        os.system("kill 1")
