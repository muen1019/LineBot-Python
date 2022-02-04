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
    
    service = build("drive", "v3", http = creds.authorize(Http()))
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
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=event.message.text))
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
            with open(os.path.join("storage", fileName),
                      "wb") as f:
                for chunk in content.iter_content():
                    f.write(chunk)
            value = upload_file(fileName, os.path.join("storage", fileName))
            if value["success"] == False:
                line_bot_api.push_message("U3e5359d656fc6d1d6610ddcb33323bde", TextSendMessage("Token已過期 請盡速更新並重新傳檔案"))
            else:
                to = To()
                fileURL = value["fileURL"]
                for i in to:
                    line_bot_api.push_message(i, TextSendMessage("大家好，我是(已經退休的)物理小老師的機器人\n以下是老師要傳給同學的檔案：\n" + fileURL + "\n其他檔案：\n" + folder_url))
                sticker = ok_sticker[randint(0, 2)]
                line_bot_api.reply_message(event.reply_token, StickerSendMessage(sticker[0], sticker[1]))
                sticker = ok_sticker[randint(0, 2)]
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
    app.run(host="0.0.0.0")
