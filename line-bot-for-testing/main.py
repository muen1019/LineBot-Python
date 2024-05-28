from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextSendMessage, FollowEvent, StickerSendMessage, FlexSendMessage, ImageSendMessage
import json
import os
from random import sample, randint
import xlrd
from bs4 import BeautifulSoup
import urllib
from fake_useragent import UserAgent
import time
import requests

app = Flask(__name__)
# line api 基本資訊
line_bot_api = LineBotApi(os.environ["ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["SECRET"])
# 儲存個人答題資訊
# state: user 狀態(get_question, get_cnt, answer, get_scope)
# mode: 測驗模式(default, wrong_question)
# title: 範圍標題
# scope: 題目課次/項目
# chinese: 單字的中文列表
# english: 單字英文列表
# sentence: 單字句子
# ans: 答案列表
# num: 第num題
# cnt: 該範圍的總題目數/已選擇之題數
# correct_num: 已答對題數
vocabulary_state = {}
need_sentence = 1

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

# 傳送Line Notify通知
def LineNotify(token, msg):
    headers = {
        "Authorization": "Bearer " + token, 
        "Content-Type" : "application/x-www-form-urlencoded"
    }

    payload = {'message': msg}
    notify = requests.post("https://notify-api.line.me/api/notify", headers = headers, params = payload)
    return notify.status_code

# 寫入錯題紀錄
def write_wrong_question(user_id, title, chinese, english):
    # 開啟原本紀錄
    try:
        with open(os.path.join("history", user_id + ".json"), "r") as f:
            obj = json.load(f)
    except:
        obj = {}
    # 同範圍已有錯題直接新增，否則建立新的範圍
    try:
        obj[title].append([chinese, english])
    except:
        obj[title] = [[chinese, english]]
    # 寫入
    json.dump(obj, open(os.path.join("history", user_id + ".json"), "w"), indent = 4)

# 讀取錯題中/英文
def read_wrong_question(user_id, title):
    value = {"have_history": True, "chinese": [], "english": []}
    # 嘗試開啟錯題紀錄
    try:
        with open(os.path.join("history", user_id + ".json"), "r") as f:
            obj = json.load(f)
        obj = obj[title]
        for i in obj:
            value["chinese"].append(i[0])
            value["english"].append(i[1])
    # 找不到紀錄
    except:
        value["have_history"] = False
    return value

# 將單字從錯題紀錄刪除
def del_wrong_question(user_id, title, chinese, english):
    # 讀檔
    with open(os.path.join("history", user_id + ".json"), "r") as f:
        obj = json.load(f)
    # 找出題目在清單中位置並刪除
    id = obj[title].index([chinese, english])
    # 範圍內已無錯題 直接刪除此項目
    if len(obj[title]) == 1: del obj[title]
    # 刪除已答對之單字
    else: del obj[title][id]
    # 寫檔
    json.dump(obj, open(os.path.join("history", user_id + ".json"), "w"), indent = 4)

# 取得網站html
def getHTML(url):
    # 取得隨機ip位置(user agent)
    headers = {'User-Agent': 'User-Agent:' + UserAgent().random}
    r = urllib.request.Request(url, headers=headers)
    # 嘗試取得html
    for _ in range(10):
        try:
            return urllib.request.urlopen(r).read()
        except:
            pass
    return urllib.request.urlopen(r).read()

# 取得例句
def get_sentence(word):
    s = time.time()
    global need_sentence
    # 片語或不須例句(不找例句))
    if " " in word or not need_sentence:
        # 只留頭尾提示
        v = list(word)
        for i in range(1, len(word) - 1):
            if v[i] != " ": v[i] = "_"
        answers = [word]
        sentences = ["".join(v)]
    else:
        try:
            # 例句之html
            soup_for_sentence = BeautifulSoup(getHTML("https://dictionary.cambridge.org/dictionary/english/" + word), "html.parser")
            # 單字變化(複數、過去式...)之html
            soup_for_changing = BeautifulSoup(getHTML("https://www.dictionary.com/browse/" + word), "html.parser")
        except:
            # 無法取得html->直接回傳題目
            v = list(word)
            for i in range(1, len(word) - 1):
                if v[i] != " ": v[i] = "_"
            answers = [word]
            sentences = ["".join(v)]
            return sentences, answers
        # 尋找例句
        sentences_html = soup_for_sentence.find_all(class_ = "eg deg") + soup_for_sentence.find_all(class_ = "deg")
        # 找單字變化
        if soup_for_changing.find_all(class_ = "css-h12q9j eejl9t60") != []:
            changing = soup_for_changing.find_all(class_ = "css-h12q9j eejl9t60")
        # 找不到其單字變化->直接使用原型
        else:   
            changing = soup_for_changing.find_all(class_ = "css-1jwcxx3 e12fnee31")
        # 找不到此單字->直接使用輸入的單字
        if soup_for_changing.find("h1").text != word.lower():
            changing = [word]
        changing.reverse()
        sentences = []
        answers = []
        # 處理每一個例句
        for sentence_html in sentences_html:
            sentence = ""
            ans = ""
            # 將零散html訊息合併成完整句子
            for j in sentence_html.children:
                try:
                    sentence += j.text
                except:
                    sentence += j
            # 嘗試單字的不同變化
            for i in changing:
                try:
                    i = i.contents[0].text
                except:
                    pass
                # 找尋句子中的單字
                if i in sentence and (sentence.find(i) + len(i) < len(sentence) and not sentence[sentence.find(i) + len(i)].isalnum()):
                    sentence = sentence.replace(i, (i[0] + "_" * (len(i) - 2) + i[-1]))
                    ans = i
                # 將字首改為大寫 再次尋找並修改
                i = i[0].upper() + i[1:]
                if i in sentence and (sentence.find(i) + len(i) < len(sentence) and not sentence[sentence.find(i) + len(i)].isalnum()):
                    sentence = sentence.replace(i, (i[0] + "_" * (len(i) - 2) + i[-1]))
                    ans = i
            # 句子中找不到單字
            if ans == "": continue
            sentence = sentence.strip(" ").strip("\n").strip(" ")
            sentences.append(sentence)
            answers.append(ans)
        # 找不到例句 直接產生題目(留字首字尾)
        if sentences == []:
            v = list(word)
            for i in range(1, len(v) - 1):
                if v[i] != " " and v[i] != "-": v[i] = "_"
            sentences.append("".join(v))
            answers.append(word)
    msg = " ".join([word, "花費", "%.2f"%(time.time() - s), "s"])
    LineNotify(os.environ["LINE_NOTIFY_TOKEN"], msg)
    print(word, "花費", "%.2f"%(time.time() - s), "s")
    return sentences, answers


# 單字測驗模式
def vocabulary(event):
    user_id = event.source.user_id
    # 進入考單字模式 詢問考試範圍
    if not user_id in vocabulary_state:
        # 初始化資料
        vocabulary_state[user_id] = {"state": "get_question", "title": "", "scope": "", "chinese": [], "english": [], "sentence": [], "ans": [], "num": -1, "cnt": -1, "correct_num": 0}
        # 設定測驗模式
        if event.message.text == "單字":
            vocabulary_state[user_id]["mode"] = "default"
            actions = []
            # 讀取目前有的範圍
            word = "請輸入考試範圍\n目前有的題目:"
            for i in os.listdir("question"):
                actions.append({
                        "type": "button",
                        "style": "link",
                        "height": "sm",
                        "action": {
                        "type": "message",
                        "label": i[0:-5],
                        "text": i[0:-5]
                        }
                })
                word += "\n" + i[0:-5]
            # 使用flex_template
            with open("flex_template.json", "r") as f:
                contents = json.load(f)
            contents["hero"]["url"] = "https://s.yimg.com/ny/api/res/1.2/OEyrjkSv6JDNXf_eIgLwHA--/YXBwaWQ9aGlnaGxhbmRlcjt3PTY0MDtoPTQwMA--/https://s.yimg.com/os/creatr-uploaded-images/2021-02/572c4830-721d-11eb-bb63-96959c3b62f2"
            contents["body"]["contents"][0]["text"] = "請選擇考試範圍"
            contents["body"]["contents"][1]["text"] = "目前有的題目 :"
            contents["footer"]["contents"] = actions
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text = word, contents = contents))
            return
        else:
            vocabulary_state[user_id]["mode"] = "wrong_question"
            # 讀取錯題紀錄
            try:
                # 讀檔
                with open(os.path.join("history", user_id + ".json"), "r") as f:
                    obj = json.load(f)
                # 無錯題紀錄
                if len(obj.keys()) == 0:
                    word = "目前沒有錯題記錄喔!"
                    del vocabulary_state[user_id]
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(word))
                    return
                else:
                    word = "目前有的錯題範圍:"
                    actions = []
                    for i in obj.keys():
                        word += "\n" + i
                        actions.append({
                            "type": "button",
                            "style": "link",
                            "height": "sm",
                            "action": {
                            "type": "message",
                            "label": i,
                            "text": i
                            }
                        })
                    with open("flex_template.json", "r") as f:
                        contents = json.load(f)
                    contents["hero"]["url"] = "https://images.chinatimes.com/newsphoto/2016-12-22/656/B18A00_P_01_02.jpg"
                    contents["body"]["contents"][0]["text"] = "請選擇錯題範圍"
                    contents["body"]["contents"][1]["text"] = "目前有 :"
                    contents["footer"]["contents"] = actions
                    line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text = word, contents = contents))
                    vocabulary_state[user_id]["state"] = "get_question"
                    return
            except:
                word = "目前沒有錯題紀錄喔!"
                del vocabulary_state[user_id]
                line_bot_api.reply_message(event.reply_token, TextSendMessage(word))
                return
    # 結束測驗模式
    if event.message.type == "text" and (event.message.text == "離開" or event.message.text == "結束"):
        del vocabulary_state[user_id]
        line_bot_api.reply_message(event.reply_token, TextSendMessage("已結束測驗模式"))
        return
    # 得到考試範圍
    if vocabulary_state[user_id]["state"] == "get_question":
        if event.message.type == "text":
            # 錯題模式 直接讀取該範圍題目
            if vocabulary_state[user_id]["mode"] == "wrong_question":
                try:
                    with open(os.path.join("history", user_id + ".json"), "r") as f:
                        obj = json.load(f)
                    obj = obj[event.message.text.upper()]
                    print(obj)
                    vocabulary_state[user_id]["state"] = "get_cnt"
                    vocabulary_state[user_id]["title"] = event.message.text.upper()
                    vocabulary_state[user_id]["cnt"] = len(obj)
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(f"請輸入題數 目前有{len(obj)}題"))
                    return
                except:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage("此範圍目前沒有錯題記錄"))
                    return
            # 預設模式 詢問課次/項目
            else:
                try:
                    with open(os.path.join("question", event.message.text.upper()) + ".json", "r") as f:
                        obj = json.load(f)
                    vocabulary_state[user_id]["title"] = event.message.text.upper()
                    vocabulary_state[user_id]["state"] = "get_scope"
                    if len(obj) > 1:
                        vocabulary_state[user_id]["state"] = "get_scope"
                        word = "請輸入課次/項目\n目前有:"
                        # 依序加入課次
                        actions = []
                        for i in sorted(obj.keys()):
                            word += "\n" + i
                            # 按鈕
                            actions.append({
                                "type": "button",
                                "style": "link",
                                "height": "sm",
                                "action": {
                                "type": "message",
                                "label": i,
                                "text": i
                                }
                            })
                        # 選單
                        with open("flex_template.json", "r") as f:
                            contents = json.load(f)
                        contents["hero"]["url"] = "https://obs.line-scdn.net/0htFZvjvvQK2lnDz0y6yJUPl1ZKAZUYzhqAzl6aiRhdV5LPT42W280WkZYdF0fOmw3DmlhD0AHMFgfOWVvUm40/w644"
                        contents["body"]["contents"][0]["text"] = "請選擇課次/項目"
                        contents["body"]["contents"][1]["text"] = "目前有 :"
                        contents["footer"]["contents"] = actions
                        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text = word, contents = contents))
                        return
                    elif len(obj) == 0:
                        vocabulary_state[user_id]["state"] = "get_question"
                        line_bot_api.reply_message(event.reply_token, TextSendMessage("很抱歉，題庫尚未建立題目，請試試其他範圍"))
                        return
                except:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage("找不到指定考試範圍題目，請再試一次"))
                    return
        else: 
            line_bot_api.reply_message(event.reply_token, TextSendMessage("請輸入考試範圍"))
            return
    # (default模式)得到考試課次/項目 詢問題目數
    if vocabulary_state[user_id]["state"] == "get_scope":
        with open(os.path.join("question", vocabulary_state[user_id]["title"]) + ".json", "r") as f:
            obj = json.load(f)
        # 設定考試範圍
        try:
            if len(obj) > 1:
                scope = event.message.text.upper()
            else:
                scope = list(obj.keys())[0]
            obj = obj[scope]
            vocabulary_state[user_id]["scope"] = scope
            vocabulary_state[user_id]["cnt"] = len(obj)
            vocabulary_state[user_id]["state"] = "get_cnt"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(f"請輸入題數\n總共有{len(obj)}題"))
            return
        # 找不到此課次/範圍
        except:
            line_bot_api.reply_message(event.reply_token, TextSendMessage("找不到指定課次/項目，請再試一次"))
            return

    # 得到題數
    if vocabulary_state[user_id]["state"] == "get_cnt":
        if not event.message.type == "text":
            line_bot_api.reply_message(event.reply_token, TextSendMessage("請輸入題數"))
            return
        elif not (event.message.text).isdigit() or int(event.message.text) <= 0:
            line_bot_api.reply_message(event.reply_token, TextSendMessage("請輸入大於0的阿拉伯數字"))
            return
        elif int(event.message.text) > vocabulary_state[user_id]["cnt"]:
            print(event.message.text)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(f"只有{vocabulary_state[user_id]['cnt']}題 請輸入小一點的數字"))
            return
        else:
            # 讀取題目
            # default模式
            if vocabulary_state[user_id]["mode"] == "default":
                with open(os.path.join("question", vocabulary_state[user_id]["title"]) + ".json", "r") as f:
                    obj = json.load(f)
                obj = obj[vocabulary_state[user_id]["scope"]]
                chinese = []
                english = []
                sentence = []
                ans = []
                for i in obj: 
                    chinese.append(i[0])
                    english.append(i[1])
                    idx = randint(0, (len(i[2]) - 1))
                    sentence.append(i[2][idx])
                    ans.append(i[3][idx])
            # 錯題模式
            else:
                with open(os.path.join("history", user_id + ".json"), "r") as f:
                    obj = json.load(f)
                chinese = []
                english = []
                ans = []
                obj = obj[vocabulary_state[user_id]["title"]]
                for i in obj: 
                    chinese.append(i[0])
                    english.append(i[1])
                    ans.append(i[1])
            # 隨機選出題目
            order = sample(range(vocabulary_state[user_id]["cnt"]), int(event.message.text))
            vocabulary_state[user_id]["chinese"] = [chinese[i] for i in order]
            vocabulary_state[user_id]["english"] = [english[i] for i in order]
            if vocabulary_state[user_id]["mode"] == "default": 
                vocabulary_state[user_id]["sentence"] = [sentence[i] for i in order]
            vocabulary_state[user_id]["ans"] = [ans[i] for i in order]
            vocabulary_state[user_id]["cnt"] = int(event.message.text)
            vocabulary_state[user_id]["state"] = "answer"
    # 作答中
    if vocabulary_state[user_id]["state"] == "answer":
        if event.message.type != "text": 
            line_bot_api.reply_message(event.reply_token, TextSendMessage("請以文字作答"))
            return
        vocabulary_state[user_id]["num"] += 1
        num = vocabulary_state[user_id]["num"]
        word = ""
        cnt = vocabulary_state[user_id]["cnt"]
        # 尚未開始作答
        if num == 0:
            word += f"共{str(cnt)}題 每題{str(100 // cnt )}分 送{str(100 % cnt)}分\n小提醒：輸入「離開」即可退出測驗模式\n--------------------\n"
        # 得到回答
        else:
            ans = vocabulary_state[user_id]['ans'][num - 1]
            # 答對
            if event.message.text.lower().strip() == ans.lower():
                word += "correct!\n"
                vocabulary_state[user_id]["correct_num"] += 1
                # 錯題模式中 刪除已答對題目
                if vocabulary_state[user_id]["mode"] == "wrong_question":
                    del_wrong_question(user_id, vocabulary_state[user_id]["title"], vocabulary_state[user_id]["chinese"][num - 1], ans)
            # 答錯
            else:
                word += f"正確答案應該是 {ans}\n"
                # 記錄錯題
                if vocabulary_state[user_id]["mode"] != "wrong_question":
                    write_wrong_question(event.source.user_id, vocabulary_state[user_id]['title'], vocabulary_state[user_id]['chinese'][num - 1], vocabulary_state[user_id]["english"][num - 1])

        # 作答結束
        if num == cnt:
            word += f"--------------------\n測驗結束!\n總分:{str((100 // cnt) * vocabulary_state[user_id]['correct_num'] + (100 % cnt))}分"
            del vocabulary_state[user_id]
        # 出題
        else:
            # default題目
            if vocabulary_state[user_id]["mode"] != "wrong_question":
                word += f"{num + 1}. {vocabulary_state[user_id]['sentence'][num]} ({vocabulary_state[user_id]['chinese'][num]})" 
            else:
                v = list(vocabulary_state[user_id]["english"][num])
                for j in range(1, len(v) - 1):
                    if v[j] != " ": v[j] = "_"
                print(vocabulary_state[user_id]["chinese"], num)
                word += f"{num + 1}. {vocabulary_state[user_id]['chinese'][num]} {''.join(v)}"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(word))
    
# 上傳題庫         
def upload_file(event):
    upload_user_id = event.source.user_id
    line_bot_api.reply_message(event.reply_token, TextSendMessage("開始上傳!"))
    # 取得檔案與檔名
    content = line_bot_api.get_message_content(str(event.message.id))
    fileName = event.message.file_name.upper()
    # 下載題目
    with open(os.path.join("storage", fileName),
              "wb") as f:
        for chunk in content.iter_content():
            f.write(chunk)
    # 讀取xlsx檔
    xlsx = xlrd.open_workbook(os.path.join("storage", fileName)) 
    d = {} # 存放題目的dictionary
    print(xlsx.sheet_names())
    # 依序讀取每個工作表
    i = 0
    for sheet_name in list(xlsx.sheet_names()):
        sheet_name = sheet_name.upper()
        d[sheet_name] = []
        sheet = xlsx.sheets()[i]
        questions = sheet.nrows
        Chinese = sheet.col_values(0)
        English = sheet.col_values(1)
        if sheet.ncols == 3: part_of_speech = sheet.col_values(2)
        for j in range(questions):
            # d[sheet_name].append([Chinese[j], English[j]])
            English[j] = str(English[j]).strip();
            sentence, ans = get_sentence(English[j])
            if sheet.ncols == 3 and part_of_speech[j] != "" : Chinese[j] = Chinese[j] + f"({part_of_speech[j]})"
            d[sheet_name].append([Chinese[j].strip(), English[j], sentence, ans])
        i += 1
    # 將題目新增至現有的題庫中
    try:
        with open(os.path.join("question", fileName[:-5] + ".json"), "r") as f:
            obj = json.load(f)
    # 開新的題庫
    except:
        obj = {}
        print("open new file")
    print("已載入:")
    for i in d.keys():
        obj[i] = d[i]
        print(i, end = " ")
    print()
    # 將題目寫入json檔
    json.dump(obj, open(os.path.join("question", fileName[:-5] + ".json"), "w"), indent = 4)
    line_bot_api.push_message(upload_user_id, TextSendMessage(f"已成功上傳{fileName.replace('XLSX', 'xlsx')}"))
        

@handler.add(MessageEvent)
def handle_message(event):
    print(event)
    # 讀取使用者狀態
    try:
        with open("state.json", "r") as f:
            globals()["vocabulary_state"][event.source.user_id] = json.load(f)[event.source.user_id]
    except:
        pass
    # 進入or已經在測驗模式
    if event.source.type == "user" and (event.source.user_id in vocabulary_state or (event.message.type == "text" and (event.message.text.strip() == "單字" or event.message.text.strip() == "錯題"))):
        vocabulary(event)
        # 讀取原先狀態
        with open("state.json", "r") as f:
            state = json.load(f)
        # 修改為結束後之狀態
        if event.source.user_id in globals()["vocabulary_state"]:
            state[event.source.user_id] = globals()["vocabulary_state"][event.source.user_id]
        else:
            del state[event.source.user_id]
        # 寫入json檔
        json.dump(state, open("state.json", "w"), indent = 4)
    # 使用說明
    elif event.message.type == "text" and (event.message.text == "說明" or event.message.text == "help"):
        line_bot_api.reply_message(event.reply_token, TextSendMessage("目前本機器人提供單字測驗服務\n單字：單字測驗\n錯題：複習錯題\n離開：結束測驗模式\n上傳格式：查看上傳題庫之格式\n例句 【1/0】：開啟／關閉自動抓取例句的模式\n\n有任何問題或bug請聯絡邱沐恩喔😊"))
    # 上傳格式說明
    elif event.message.type == "text" and (event.message.text == "上傳格式" or event.message.text.strip()  == "upload form"):
        line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url = "https://i.imgur.com/EAV7gx4.jpg", preview_image_url = "https://i.imgur.com/EAV7gx4.jpg"))
        # line_bot_api.reply_message(event.reply_token, TextSendMessage("請使用excel格式(.xlsx)\n檔案名稱設為「考試範圍」\n工作表名稱設為「課次/項目」\n\n第一列請打中文\n第二列請打英文\n上傳後系統會自動從網路上抓例句"))
    # 檢查是否有人在答題
    elif event.message.type == "text" and event.source.type == "user" and event.message.text == "狀態" and event.source.user_id == "U3e5359d656fc6d1d6610ddcb33323bde":
        user = []
        with open("state.json", "r") as f:
            state = json.load(f)
        for i in state.keys():
            user.append(line_bot_api.get_profile(i).display_name)
        if len(user) == 0:
            line_bot_api.reply_message(event.reply_token, TextSendMessage("目前無人使用"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(f"目前{' '.join(user)}正在使用，共{len(user)}人"))
    # 開關尋找例句功能
    elif event.message.type == "text" and "例句" in event.message.text:
        global need_sentence
        if event.message.text == "例句": 
            if need_sentence:
                line_bot_api.reply_message(event.reply_token, TextSendMessage("已開啟自動抓取例句"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage("未開啟自動抓取例句"))
        else:
            yes = event.message.text[3:]
            if not yes.isdigit():
                line_bot_api.reply_message(event.reply_token, TextSendMessage("輸入格式為「例句 1(開啟)/0(關閉)」"))
            elif yes == "0":
                need_sentence = 0
                line_bot_api.reply_message(event.reply_token, TextSendMessage("已關閉自動抓取例句"))
            else:
                need_sentence = 1
                line_bot_api.reply_message(event.reply_token, TextSendMessage("已開啟自動抓取例句"))
    # 上傳題庫
    elif event.message.type == 'file' and event.message.file_name[-4:] == "xlsx":
      	upload_file(event)
    elif event.message.type == "text":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(event.message.text))
    else:
        line_bot_api.reply_message(event.reply_token, StickerSendMessage("6362", "11087936"))

@handler.add(FollowEvent)
def handler_follow(event):
    print(event)
    with open("user.txt", "a") as f:
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